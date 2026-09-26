import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils.timezone import now

from plataforma.models import AnalyticsEvent, AnalyticsSession, Portal
from plataforma.services.adaptive_engine import Insight, analisar, calcular, detectar, gerar, ler, preparar_contexto
from plataforma.services.adaptive_engine.bottlenecks import (
    LIMIAR_BAIXA_PASSAGEM,
    LIMIAR_CHECKOUT_DIRETO,
    LIMIAR_QUEDA_TRAFEGO,
    LIMIAR_VARIACAO_CONVERSAO,
)
from plataforma.services.adaptive_engine.metrics import AMOSTRA_MINIMA
from plataforma.services.analytics import montar_dashboard


class LeituraAdaptiveEngineTests(TestCase):
    def setUp(self):
        self.p1 = Portal.objects.create(nome='Portal A', slug='portal-a-ae', cidade='X', estado='RO')
        self.p2 = Portal.objects.create(nome='Portal B', slug='portal-b-ae', cidade='Y', estado='RO')
        self.sessao_a = self._sessao(portal=self.p1)
        self.sessao_b = self._sessao(portal=self.p2)
        self.evento_a = AnalyticsEvent.objects.create(
            sessao=self.sessao_a, portal=self.p1, tipo='view_home', path='/',
        )
        self.evento_b = AnalyticsEvent.objects.create(
            sessao=self.sessao_b, portal=self.p2, tipo='view_plans', path='/comece/',
        )

    def _sessao(self, portal=None):
        uid = uuid.uuid4()
        return AnalyticsSession.objects.create(
            id=uid,
            rotulo=uid.hex[:4].upper(),
            visto_em=now(),
            path_primeiro='/',
            path_atual='/',
            portal=portal,
        )

    def _recuar(self, registro, dias):
        registro.criado_em = now() - timedelta(days=dias)
        registro.save(update_fields=['criado_em'])

    def test_le_eventos_gravados(self):
        dados = ler({'periodo': 'hoje'})
        ids = set(dados['eventos'].values_list('id', flat=True))
        self.assertIn(self.evento_a.id, ids)
        self.assertIn(self.evento_b.id, ids)
        self.assertEqual(dados['eventos'].get(pk=self.evento_a.id).tipo, 'view_home')

    def test_le_sessoes_gravadas(self):
        dados = ler({'periodo': 'hoje'})
        ids = set(dados['sessoes'].values_list('id', flat=True))
        self.assertIn(self.sessao_a.id, ids)
        self.assertIn(self.sessao_b.id, ids)

    def test_filtra_por_periodo(self):
        antigo = AnalyticsEvent.objects.create(
            sessao=self.sessao_a, portal=self.p1, tipo='click_plan', path='/comece/basico/',
        )
        self._recuar(antigo, 2)
        self._recuar(self.sessao_b, 2)
        hoje = ler({'periodo': 'hoje'})
        self.assertNotIn(antigo.id, set(hoje['eventos'].values_list('id', flat=True)))
        self.assertNotIn(self.sessao_b.id, set(hoje['sessoes'].values_list('id', flat=True)))
        semana = ler({'periodo': '7d'})
        self.assertIn(antigo.id, set(semana['eventos'].values_list('id', flat=True)))
        self.assertIn(self.sessao_b.id, set(semana['sessoes'].values_list('id', flat=True)))

    def test_filtra_por_portal(self):
        dados = ler({'periodo': 'hoje', 'portal': str(self.p1.pk)})
        self.assertEqual(dados['portal'].pk, self.p1.pk)
        self.assertEqual(set(dados['eventos'].values_list('id', flat=True)), {self.evento_a.id})
        self.assertEqual(set(dados['sessoes'].values_list('id', flat=True)), {self.sessao_a.id})

    def test_leitura_nao_altera_registros(self):
        antes_eventos = list(
            AnalyticsEvent.objects.order_by('id').values_list('id', 'tipo', 'path', 'portal_id', 'sessao_id')
        )
        antes_sessoes = list(
            AnalyticsSession.objects.order_by('id').values_list('id', 'rotulo', 'portal_id', 'path_atual')
        )
        list(ler({'periodo': 'hoje'})['eventos'])
        list(ler({'periodo': 'hoje', 'portal': str(self.p1.pk)})['sessoes'])
        self.assertEqual(
            list(AnalyticsEvent.objects.order_by('id').values_list('id', 'tipo', 'path', 'portal_id', 'sessao_id')),
            antes_eventos,
        )
        self.assertEqual(
            list(AnalyticsSession.objects.order_by('id').values_list('id', 'rotulo', 'portal_id', 'path_atual')),
            antes_sessoes,
        )

    def test_leitura_nao_cria_evento(self):
        eventos = AnalyticsEvent.objects.count()
        sessoes = AnalyticsSession.objects.count()
        ler({'periodo': 'hoje'})
        ler({'periodo': '7d', 'portal': str(self.p2.pk)})
        self.assertEqual(AnalyticsEvent.objects.count(), eventos)
        self.assertEqual(AnalyticsSession.objects.count(), sessoes)

    def test_isolamento_entre_portais(self):
        a = ler({'periodo': 'hoje', 'portal': str(self.p1.pk)})
        b = ler({'periodo': 'hoje', 'portal': str(self.p2.pk)})
        ids_a = set(a['eventos'].values_list('portal_id', flat=True))
        ids_b = set(b['eventos'].values_list('portal_id', flat=True))
        self.assertEqual(ids_a, {self.p1.pk})
        self.assertEqual(ids_b, {self.p2.pk})
        self.assertFalse(set(a['sessoes'].values_list('id', flat=True)) & set(b['sessoes'].values_list('id', flat=True)))

    def test_evento_do_portal_entra_mesmo_com_sessao_sem_portal(self):
        solta = self._sessao(portal=None)
        evento = AnalyticsEvent.objects.create(
            sessao=solta, portal=self.p1, tipo='portal_created', path='/app/comecar/',
        )
        dados = ler({'periodo': 'hoje', 'portal': str(self.p1.pk)})
        self.assertIn(evento.id, set(dados['eventos'].values_list('id', flat=True)))
        self.assertIn(solta.id, set(dados['sessoes'].values_list('id', flat=True)))
        outro = ler({'periodo': 'hoje', 'portal': str(self.p2.pk)})
        self.assertNotIn(evento.id, set(outro['eventos'].values_list('id', flat=True)))
        self.assertNotIn(solta.id, set(outro['sessoes'].values_list('id', flat=True)))


class MetricasAdaptiveEngineTests(TestCase):
    def _sessao(self, **extra):
        uid = uuid.uuid4()
        dados = {
            'id': uid,
            'rotulo': uid.hex[:4].upper(),
            'visto_em': now(),
            'path_primeiro': '/',
            'path_atual': '/',
        }
        dados.update(extra)
        return AnalyticsSession.objects.create(**dados)

    def _evento(self, sessao, tipo, path='/', portal=None, extra=None):
        return AnalyticsEvent.objects.create(
            sessao=sessao, portal=portal, tipo=tipo, path=path, extra=extra or {},
        )

    def test_periodo_sem_dados_nao_devolve_zero(self):
        dados = calcular({'periodo': 'hoje'})
        self.assertEqual(dados['aquisicao']['sessoes']['valor'], None)
        self.assertEqual(dados['aquisicao']['sessoes']['estado'], 'sem_amostra')
        self.assertEqual(dados['funil_pago']['cliques']['valor'], None)
        self.assertEqual(dados['compras']['receita']['valor'], None)
        self.assertEqual(dados['conversoes']['pago_clique_para_checkout']['estado'], 'sem_amostra')

    def test_divisao_por_zero_devolve_sem_amostra(self):
        sessao = self._sessao()
        self._evento(sessao, 'view_home')
        dados = calcular({'periodo': 'hoje'})
        taxa = dados['conversoes']['pago_clique_para_checkout']
        self.assertIsNone(taxa['valor'])
        self.assertEqual(taxa['estado'], 'sem_amostra')
        self.assertEqual(dados['funil_pago']['cliques']['valor'], 0)

    def test_pouca_amostra_marca_baixa_confianca(self):
        sessao = self._sessao()
        self._evento(sessao, 'click_plan', '/comece/basico/', extra={'plano': 'basico'})
        self._evento(sessao, 'initiate_checkout', '/comece/basico/')
        dados = calcular({'periodo': 'hoje'})
        taxa = dados['conversoes']['pago_clique_para_checkout']
        self.assertEqual(taxa['valor'], 1.0)
        self.assertEqual(taxa['estado'], 'baixa_confianca')
        self.assertLess(taxa['amostra'], AMOSTRA_MINIMA)

    def test_amostra_suficiente_marca_ok(self):
        for _ in range(AMOSTRA_MINIMA):
            sessao = self._sessao()
            self._evento(sessao, 'click_plan', '/comece/basico/')
            self._evento(sessao, 'initiate_checkout', '/comece/basico/')
        taxa = calcular({'periodo': 'hoje'})['conversoes']['pago_clique_para_checkout']
        self.assertEqual(taxa['valor'], 1.0)
        self.assertEqual(taxa['estado'], 'ok')
        self.assertEqual(taxa['amostra'], AMOSTRA_MINIMA)

    def test_funil_gratis_e_pago_seguem_a_fase_a(self):
        gratis = self._sessao()
        self._evento(gratis, 'click_subscribe', '/app/comecar/')
        self._evento(gratis, 'portal_created', '/app/comecar/')
        pago = self._sessao()
        self._evento(pago, 'click_plan', '/comece/basico/', extra={'plano': 'basico'})
        self._evento(pago, 'initiate_checkout', '/comece/basico/')
        direto = self._sessao()
        self._evento(direto, 'initiate_checkout', '/comece/profissional/')
        comparacao = self._sessao()
        self._evento(comparacao, 'view_plans', '/comece/')
        dados = calcular({'periodo': 'hoje'})
        self.assertEqual(dados['funil_gratis']['cliques']['valor'], 1)
        self.assertEqual(dados['funil_gratis']['portal_no_fluxo']['valor'], 1)
        self.assertEqual(dados['funil_gratis']['sem_clique']['valor'], 0)
        self.assertEqual(dados['conversoes']['gratis_clique_para_portal']['valor'], 1.0)
        self.assertEqual(dados['funil_pago']['cliques']['valor'], 1)
        self.assertEqual(dados['funil_pago']['checkout_no_fluxo']['valor'], 1)
        self.assertEqual(dados['checkout_direto']['sessoes']['valor'], 1)
        self.assertEqual(dados['checkout_direto']['proporcao']['valor'], 0.5)
        self.assertEqual(dados['funil_comparacao']['view_plans']['valor'], 1)
        self.assertNotIn('purchase', dados['funil_pago'])

    def test_compras_orfa_e_receita(self):
        orfa = self._sessao()
        self._evento(orfa, 'purchase', '/comece/', extra={'valor': '29.90'})
        ligada = self._sessao()
        self._evento(ligada, 'view_home', '/')
        self._evento(ligada, 'purchase', '/comece/', extra={'valor': '10.00'})
        dados = calcular({'periodo': 'hoje'})
        self.assertEqual(dados['compras']['sessoes']['valor'], 2)
        self.assertEqual(dados['compras']['orfas']['valor'], 1)
        self.assertEqual(dados['compras']['receita']['valor'], Decimal('39.90'))

    def test_conversao_por_dispositivo_origem_e_plano(self):
        mobile = self._sessao(dispositivo=AnalyticsSession.DISPOSITIVO_MOBILE, utm_source='ig')
        self._evento(mobile, 'click_plan', '/comece/basico/', extra={'plano': 'basico'})
        desktop = self._sessao(dispositivo=AnalyticsSession.DISPOSITIVO_DESKTOP, utm_source='google')
        self._evento(desktop, 'click_plan', '/comece/profissional/', extra={'plano': 'profissional'})
        self._evento(desktop, 'initiate_checkout', '/comece/profissional/')
        dados = calcular({'periodo': 'hoje'})
        por_dispositivo = {item['chave']: item['taxa']['valor'] for item in dados['conversoes']['pago_por_dispositivo']['itens']}
        self.assertEqual(por_dispositivo['Mobile'], 0.0)
        self.assertEqual(por_dispositivo['Desktop'], 1.0)
        por_plano = {item['chave']: item['taxa']['valor'] for item in dados['conversoes']['pago_por_plano']['itens']}
        self.assertEqual(por_plano['basico'], 0.0)
        self.assertEqual(por_plano['profissional'], 1.0)
        self.assertTrue(dados['conversoes']['pago_por_origem']['itens'])

    def test_comparacao_com_periodo_anterior(self):
        sessao = self._sessao()
        evento = self._evento(sessao, 'click_plan', '/comece/basico/')
        ontem = now() - timedelta(days=1)
        sessao.criado_em = ontem
        sessao.save(update_fields=['criado_em'])
        evento.criado_em = ontem
        evento.save(update_fields=['criado_em'])
        dados = calcular({'periodo': 'hoje'})
        self.assertIsNone(dados['funil_pago']['cliques']['valor'])
        self.assertEqual(dados['comparacao']['funil_pago']['cliques']['valor'], 1)
        self.assertNotIn('comparacao', dados['comparacao'])

    def test_isolamento_de_portal_nas_metricas(self):
        p1 = Portal.objects.create(nome='M1', slug='portal-m1-ae', cidade='X', estado='RO')
        p2 = Portal.objects.create(nome='M2', slug='portal-m2-ae', cidade='Y', estado='RO')
        s1 = self._sessao(portal=p1)
        s2 = self._sessao(portal=p2)
        self._evento(s1, 'purchase', '/comece/', portal=p1, extra={'valor': '29.90'})
        self._evento(s2, 'purchase', '/comece/', portal=p2, extra={'valor': '49.90'})
        a = calcular({'periodo': 'hoje', 'portal': str(p1.pk)})
        b = calcular({'periodo': 'hoje', 'portal': str(p2.pk)})
        self.assertEqual(a['compras']['receita']['valor'], Decimal('29.90'))
        self.assertEqual(b['compras']['receita']['valor'], Decimal('49.90'))
        self.assertEqual(a['compras']['sessoes']['valor'], 1)
        self.assertEqual(b['compras']['sessoes']['valor'], 1)

    def test_metricas_nao_alteram_registros(self):
        sessao = self._sessao()
        self._evento(sessao, 'view_home')
        antes = AnalyticsEvent.objects.count()
        calcular({'periodo': 'hoje'})
        self.assertEqual(AnalyticsEvent.objects.count(), antes)
        self.assertEqual(AnalyticsEvent.objects.get().tipo, 'view_home')

    def test_fase_a_continua_calculando_o_dashboard(self):
        sessao = self._sessao()
        self._evento(sessao, 'view_home', '/')
        self._evento(sessao, 'purchase', '/comece/', extra={'valor': '29.90'})
        calcular({'periodo': 'hoje'})
        painel = montar_dashboard({'periodo': 'hoje'})
        self.assertEqual(painel['compras'], 1)
        self.assertEqual(painel['compras_orfas'], 0)
        self.assertIn('funil_pago', painel)
        self.assertIn('funil_gratis', painel)


class GargalosAdaptiveEngineTests(TestCase):
    def _sessao(self):
        uid = uuid.uuid4()
        return AnalyticsSession.objects.create(
            id=uid, rotulo=uid.hex[:4].upper(), visto_em=now(),
            path_primeiro='/', path_atual='/',
        )

    def _evento(self, sessao, tipo, path='/'):
        return AnalyticsEvent.objects.create(sessao=sessao, tipo=tipo, path=path, extra={})

    def _recuar(self, registros):
        ontem = now() - timedelta(days=1)
        for registro in registros:
            registro.criado_em = ontem
            registro.save(update_fields=['criado_em'])

    def _tipos(self, dados):
        return [item['tipo'] for item in dados['gargalos']]

    def test_funil_gratis_dispara_com_amostra_suficiente(self):
        for indice in range(AMOSTRA_MINIMA):
            sessao = self._sessao()
            self._evento(sessao, 'click_subscribe', '/app/comecar/')
            if indice < 2:
                self._evento(sessao, 'portal_created', '/app/comecar/')
        dados = detectar({'periodo': 'hoje'})
        gargalo = next(item for item in dados['gargalos'] if item['area'] == 'funil_gratis')
        self.assertEqual(gargalo['tipo'], 'baixa_passagem')
        self.assertEqual(gargalo['etapa'], 'click_subscribe → portal_created')
        self.assertEqual(gargalo['taxa_observada'], round(2 / AMOSTRA_MINIMA, 4))
        self.assertEqual(gargalo['amostra'], AMOSTRA_MINIMA)
        self.assertEqual(gargalo['confianca'], 'media')
        self.assertEqual(gargalo['limiar_usado'], LIMIAR_BAIXA_PASSAGEM)

    def test_funil_gratis_nao_dispara_com_amostra_pequena(self):
        for _ in range(5):
            sessao = self._sessao()
            self._evento(sessao, 'click_subscribe', '/app/comecar/')
        dados = detectar({'periodo': 'hoje'})
        self.assertNotIn('baixa_passagem', self._tipos(dados))
        self.assertEqual(dados['compras']['estado'], 'amostra_insuficiente')
        self.assertFalse(dados['compras']['gargalo'])

    def test_funil_pago_dispara_com_taxa_baixa(self):
        for indice in range(40):
            sessao = self._sessao()
            self._evento(sessao, 'click_plan', '/comece/basico/')
            if indice < 5:
                self._evento(sessao, 'initiate_checkout', '/comece/basico/')
        gargalo = next(item for item in detectar({'periodo': 'hoje'})['gargalos'] if item['area'] == 'funil_pago')
        self.assertEqual(gargalo['tipo'], 'baixa_passagem')
        self.assertEqual(gargalo['taxa_observada'], round(5 / 40, 4))
        self.assertEqual(gargalo['limiar_usado'], LIMIAR_BAIXA_PASSAGEM)
        self.assertEqual(gargalo['confianca'], 'media')

    def test_checkout_direto_dispara_acima_do_limiar(self):
        for _ in range(AMOSTRA_MINIMA):
            self._evento(self._sessao(), 'initiate_checkout', '/comece/basico/')
        gargalo = next(item for item in detectar({'periodo': 'hoje'})['gargalos'] if item['tipo'] == 'checkout_direto')
        self.assertEqual(gargalo['taxa_observada'], 1.0)
        self.assertEqual(gargalo['limiar_usado'], LIMIAR_CHECKOUT_DIRETO)
        self.assertNotIn('problema', gargalo['descricao'].lower())

    def test_ausencia_de_compras_nao_vira_gargalo(self):
        for _ in range(5):
            self._evento(self._sessao(), 'view_home', '/')
        dados = detectar({'periodo': 'hoje'})
        self.assertEqual(dados['compras']['estado'], 'amostra_insuficiente')
        self.assertFalse(dados['compras']['gargalo'])
        self.assertFalse(any(item['area'] == 'compras' for item in dados['gargalos']))

    def test_queda_de_trafego_dispara_com_variacao_relevante(self):
        hoje = [self._sessao() for _ in range(AMOSTRA_MINIMA)]
        ontem = [self._sessao() for _ in range(AMOSTRA_MINIMA * 2)]
        self._recuar(ontem)
        gargalo = next(item for item in detectar({'periodo': 'hoje'})['gargalos'] if item['tipo'] == 'queda_de_trafego')
        self.assertEqual(gargalo['variacao'], -0.5)
        self.assertEqual(gargalo['valor_atual'], AMOSTRA_MINIMA)
        self.assertEqual(gargalo['valor_anterior'], AMOSTRA_MINIMA * 2)
        self.assertEqual(gargalo['limiar_usado'], LIMIAR_QUEDA_TRAFEGO)
        self.assertEqual(len(hoje), AMOSTRA_MINIMA)

    def test_queda_de_trafego_nao_dispara_dentro_do_esperado(self):
        hoje = [self._sessao() for _ in range(AMOSTRA_MINIMA)]
        ontem = [self._sessao() for _ in range(34)]
        self._recuar(ontem)
        dados = detectar({'periodo': 'hoje'})
        self.assertNotIn('queda_de_trafego', self._tipos(dados))
        self.assertEqual(len(hoje), AMOSTRA_MINIMA)

    def test_variacao_de_conversao_exige_amostra_nos_dois_periodos(self):
        for _ in range(AMOSTRA_MINIMA):
            sessao = self._sessao()
            self._evento(sessao, 'click_plan', '/comece/basico/')
            self._evento(sessao, 'initiate_checkout', '/comece/basico/')
        poucos = []
        for _ in range(2):
            sessao = self._sessao()
            evento = self._evento(sessao, 'click_plan', '/comece/basico/')
            poucos.extend([sessao, evento])
        self._recuar(poucos)
        dados = detectar({'periodo': 'hoje'})
        self.assertNotIn('variacao_de_conversao', self._tipos(dados))

    def test_variacao_de_conversao_dispara_com_amostra_nos_dois_periodos(self):
        for _ in range(AMOSTRA_MINIMA):
            sessao = self._sessao()
            self._evento(sessao, 'click_plan', '/comece/basico/')
            self._evento(sessao, 'initiate_checkout', '/comece/basico/')
        anteriores = []
        for _ in range(AMOSTRA_MINIMA):
            sessao = self._sessao()
            evento = self._evento(sessao, 'click_plan', '/comece/basico/')
            anteriores.extend([sessao, evento])
        self._recuar(anteriores)
        gargalo = next(
            item for item in detectar({'periodo': 'hoje'})['gargalos']
            if item['tipo'] == 'variacao_de_conversao' and item['area'] == 'funil_pago'
        )
        self.assertEqual(gargalo['valor_atual'], 1.0)
        self.assertEqual(gargalo['valor_anterior'], 0.0)
        self.assertEqual(gargalo['variacao'], 1.0)
        self.assertEqual(gargalo['limiar_usado'], LIMIAR_VARIACAO_CONVERSAO)
        self.assertEqual(gargalo['amostra'], AMOSTRA_MINIMA)

    def test_mesma_entrada_produz_a_mesma_saida(self):
        for indice in range(AMOSTRA_MINIMA):
            sessao = self._sessao()
            self._evento(sessao, 'click_subscribe', '/app/comecar/')
            if indice < 2:
                self._evento(sessao, 'portal_created', '/app/comecar/')
        self.assertEqual(detectar({'periodo': 'hoje'}), detectar({'periodo': 'hoje'}))

    def test_detector_nao_altera_registros_nem_a_fase_a(self):
        sessao = self._sessao()
        self._evento(sessao, 'view_home', '/')
        antes = AnalyticsEvent.objects.count()
        detectar({'periodo': 'hoje'})
        self.assertEqual(AnalyticsEvent.objects.count(), antes)
        painel = montar_dashboard({'periodo': 'hoje'})
        self.assertIn('funil_pago', painel)
        self.assertIn('funil_gratis', painel)

    def test_descricoes_nao_afirmam_causa(self):
        for _ in range(AMOSTRA_MINIMA):
            self._evento(self._sessao(), 'initiate_checkout', '/comece/basico/')
        for indice in range(AMOSTRA_MINIMA):
            sessao = self._sessao()
            self._evento(sessao, 'click_subscribe', '/app/comecar/')
            if indice < 2:
                self._evento(sessao, 'portal_created', '/app/comecar/')
        proibidos = ('porque', 'causou', 'problema', 'anúncio', 'seo', 'algoritmo', 'falha')
        for item in detectar({'periodo': 'hoje'})['gargalos']:
            texto = item['descricao'].lower()
            self.assertTrue(item['limiar_usado'])
            for termo in proibidos:
                self.assertNotIn(termo, texto)


class InsightsAdaptiveEngineTests(TestCase):
    def _gargalo(self, **extra):
        dados = {
            'tipo': 'baixa_passagem',
            'area': 'funil_gratis',
            'etapa': 'click_subscribe → portal_created',
            'descricao': 'padrao',
            'taxa_observada': 0.0667,
            'variacao': None,
            'amostra': 30,
            'amostra_anterior': None,
            'valor_atual': 0.0667,
            'valor_anterior': None,
            'confianca': 'media',
            'limiar_usado': 0.20,
        }
        dados.update(extra)
        return dados

    def _metricas_gratis(self):
        return {
            'funil_gratis': {
                'cliques': {'valor': 30},
                'portal_no_fluxo': {'valor': 2},
            },
        }

    def _textos(self, insight):
        return ' '.join([
            insight.titulo, insight.resumo, insight.hipotese, insight.acao_sugerida,
        ]).lower()

    def test_funil_gratis_gera_insight_com_evidencia_e_confianca(self):
        insight = gerar(self._metricas_gratis(), [self._gargalo()])[0]
        self.assertIsInstance(insight, Insight)
        self.assertEqual(insight.id, 'funil_gratis_baixa_passagem')
        self.assertEqual(insight.confianca, 'media')
        self.assertEqual(insight.amostra, 30)
        evidencias = {item['metrica']: item['valor'] for item in insight.evidencias}
        self.assertEqual(evidencias['click_subscribe'], 30)
        self.assertEqual(evidencias['portal_created'], 2)
        self.assertEqual(evidencias['taxa'], 0.0667)
        self.assertIn('hipótese', insight.hipotese.lower())
        self.assertIn('pode', insight.hipotese.lower())

    def test_funil_gratis_nao_gera_sem_gargalo(self):
        self.assertEqual(gerar(self._metricas_gratis(), []), [])

    def test_confianca_alta_e_preservada(self):
        insight = gerar(self._metricas_gratis(), [self._gargalo(confianca='alta', amostra=100)])[0]
        self.assertEqual(insight.confianca, 'alta')

    def test_funil_pago_gera_e_ausente_nao_gera(self):
        metricas = {'funil_pago': {'cliques': {'valor': 40}, 'checkout_no_fluxo': {'valor': 5}}}
        gargalo = self._gargalo(
            tipo='baixa_passagem', area='funil_pago', taxa_observada=0.125,
            valor_atual=0.125, amostra=40,
        )
        insight = gerar(metricas, [gargalo])[0]
        self.assertEqual(insight.id, 'funil_pago_baixa_passagem')
        evidencias = {item['metrica']: item['valor'] for item in insight.evidencias}
        self.assertEqual(evidencias['click_plan'], 40)
        self.assertEqual(evidencias['initiate_checkout'], 5)
        self.assertEqual(gerar(metricas, []), [])

    def test_checkout_direto_gera_e_amostra_pequena_nao_gera(self):
        metricas = {'checkout_direto': {'sessoes': {'valor': 30}}}
        gargalo = self._gargalo(
            tipo='checkout_direto', area='checkout', taxa_observada=1.0,
            valor_atual=1.0, amostra=30, limiar_usado=0.50,
        )
        insight = gerar(metricas, [gargalo])[0]
        self.assertEqual(insight.id, 'checkout_direto')
        self.assertEqual(insight.confianca, 'media')
        pequeno = self._gargalo(
            tipo='checkout_direto', area='checkout', taxa_observada=1.0,
            amostra=5, confianca='baixa',
        )
        self.assertEqual(gerar(metricas, [pequeno]), [])

    def test_queda_de_trafego_gera_insight(self):
        gargalo = self._gargalo(
            tipo='queda_de_trafego', area='trafego', variacao=-0.5,
            valor_atual=100, valor_anterior=200, amostra=100, confianca='alta',
            taxa_observada=None,
        )
        insight = gerar({}, [gargalo])[0]
        self.assertEqual(insight.id, 'queda_de_trafego')
        self.assertEqual(insight.variacao, -0.5)
        self.assertIn('50%', insight.resumo)
        self.assertNotIn('meta', insight.resumo.lower())

    def test_queda_dentro_do_esperado_nao_gera_sem_gargalo(self):
        self.assertEqual(gerar({}, []), [])

    def test_variacao_de_conversao_gera_e_amostra_pequena_nao_gera(self):
        gargalo = self._gargalo(
            tipo='variacao_de_conversao', area='funil_pago', variacao=-0.15,
            valor_atual=0.03, valor_anterior=0.18, amostra=40, amostra_anterior=40,
            taxa_observada=0.03,
        )
        insight = gerar({}, [gargalo])[0]
        self.assertEqual(insight.id, 'variacao_conversao_funil_pago')
        self.assertEqual(insight.como_dict()['evidencias'][0]['valor'], 0.03)
        self.assertIn('pode', insight.hipotese.lower())
        curto = self._gargalo(
            tipo='variacao_de_conversao', area='funil_pago', variacao=-0.15,
            amostra=10, confianca='baixa',
        )
        self.assertEqual(gerar({}, [curto]), [])

    def test_textos_observam_e_tratam_hipotese_como_hipotese(self):
        gargalos = [
            self._gargalo(),
            self._gargalo(tipo='checkout_direto', area='checkout', taxa_observada=0.8, valor_atual=0.8),
        ]
        proibidos = ('porque', 'causou', 'problema', 'anúncio', 'seo', 'algoritmo', 'falha')
        acoes = ('mudar preço', 'alterar o checkout', 'criar campanha', 'pausar anúncio', 'mudar a home')
        for insight in gerar(self._metricas_gratis(), gargalos):
            texto = self._textos(insight)
            self.assertIn('hipótese', insight.hipotese.lower())
            for termo in proibidos:
                self.assertNotIn(termo, texto)
            for termo in acoes:
                self.assertNotIn(termo, insight.acao_sugerida.lower())

    def test_ordem_fixa_e_deterministica(self):
        gargalos = [
            self._gargalo(tipo='queda_de_trafego', area='trafego', variacao=-0.4, valor_atual=60, valor_anterior=100),
            self._gargalo(tipo='checkout_direto', area='checkout', taxa_observada=0.7, valor_atual=0.7),
            self._gargalo(tipo='baixa_passagem', area='funil_pago', taxa_observada=0.1, valor_atual=0.1),
            self._gargalo(),
        ]
        primeira = [item.id for item in gerar({}, gargalos)]
        segunda = [item.id for item in gerar({}, list(reversed(gargalos)))]
        self.assertEqual(primeira, [
            'funil_gratis_baixa_passagem',
            'funil_pago_baixa_passagem',
            'checkout_direto',
            'queda_de_trafego',
        ])
        self.assertEqual(primeira, segunda)

    def test_gerar_nao_altera_entrada_nem_registros(self):
        sessao_id = uuid.uuid4()
        AnalyticsSession.objects.create(
            id=sessao_id, rotulo='ZZZ1', visto_em=now(),
            path_primeiro='/', path_atual='/',
        )
        AnalyticsEvent.objects.create(
            sessao_id=sessao_id, tipo='view_home', path='/', extra={},
        )
        antes = AnalyticsEvent.objects.count()
        gargalos = [self._gargalo()]
        copia = [dict(gargalos[0])]
        gerar(self._metricas_gratis(), gargalos)
        self.assertEqual(gargalos, copia)
        self.assertEqual(AnalyticsEvent.objects.count(), antes)
        self.assertEqual(AnalyticsEvent.objects.get().tipo, 'view_home')

    def test_isolamento_entre_payloads(self):
        a = gerar(
            {'funil_gratis': {'cliques': {'valor': 30}, 'portal_no_fluxo': {'valor': 2}}},
            [self._gargalo(taxa_observada=0.0667)],
        )[0]
        b = gerar(
            {'funil_gratis': {'cliques': {'valor': 30}, 'portal_no_fluxo': {'valor': 10}}},
            [self._gargalo(taxa_observada=0.3333)],
        )[0]
        self.assertEqual(a.evidencias[1]['valor'], 2)
        self.assertEqual(b.evidencias[1]['valor'], 10)
        self.assertNotEqual(a.resumo, b.resumo)


class IaAdaptiveEngineTests(TestCase):
    def _resposta(self, **extra):
        dados = {
            'resumo': 'Foi observada baixa passagem no funil gratuito.',
            'observacoes': ['Os dados mostram 30 cliques e 2 portais criados.'],
            'hipoteses': ['Uma hipótese a investigar é a etapa entre o clique e a criação.'],
            'acoes_sugeridas': ['Seria necessário testar o caminho antes de alterar algo.'],
        }
        dados.update(extra)
        return dados

    def _metricas(self, portal_id=1, sessoes=247):
        return {
            'periodo': 'hoje',
            'portal_id': portal_id,
            'aquisicao': {'sessoes': {'valor': sessoes}},
            'sessao_id': 'e82198c9-2ce2-4d7a-9e0d-8b2a12daf3c3',
            'email': 'ana@test.com',
            'api_key': 'sk-live-secret',
            'pup_aid': 'cookie-secreto',
            'utm_campaign': 'IGNORE PREVIOUS\nana@test.com',
        }

    def test_contexto_reune_metricas_gargalos_e_insights(self):
        gargalo = {'tipo': 'baixa_passagem', 'area': 'funil_gratis', 'amostra': 30, 'confianca': 'media'}
        insight = Insight(
            id='funil_gratis_baixa_passagem', tipo='baixa_passagem', area='funil_gratis',
            titulo='Baixa passagem', resumo='Foi observada baixa passagem.',
            evidencias=[{'metrica': 'taxa', 'valor': 0.0667}], amostra=30,
            confianca='media', variacao=None, hipotese='Hipótese: pode merecer investigação.',
            acao_sugerida='Investigar a etapa.',
        )
        contexto = preparar_contexto(self._metricas(), [gargalo], [insight])
        self.assertEqual(contexto['metricas']['aquisicao']['sessoes']['valor'], 247)
        self.assertEqual(contexto['gargalos'][0]['tipo'], 'baixa_passagem')
        self.assertEqual(contexto['insights'][0]['id'], 'funil_gratis_baixa_passagem')
        self.assertEqual(contexto['periodo'], 'hoje')

    def test_contexto_exclui_dados_sensiveis_e_e_deterministico(self):
        gargalo = {'tipo': 'baixa_passagem', 'amostra': 30}
        primeiro = preparar_contexto(self._metricas(), [gargalo], [])
        segundo = preparar_contexto(self._metricas(), [gargalo], [])
        self.assertEqual(primeiro, segundo)
        texto = str(primeiro)
        self.assertNotIn('e82198c9', texto)
        self.assertNotIn('ana@test.com', texto)
        self.assertNotIn('sk-live', texto)
        self.assertNotIn('cookie-secreto', texto)
        self.assertNotIn('\n', primeiro['metricas']['utm_campaign'])
        self.assertNotIn('sessao_id', primeiro['metricas'])
        self.assertNotIn('api_key', primeiro['metricas'])

    def test_contexto_nao_consulta_banco_nem_altera_entrada(self):
        uid = uuid.uuid4()
        AnalyticsSession.objects.create(
            id=uid, rotulo='IA01', visto_em=now(), path_primeiro='/', path_atual='/',
        )
        AnalyticsEvent.objects.create(sessao_id=uid, tipo='view_home', path='/', extra={})
        antes = AnalyticsEvent.objects.count()
        metricas = self._metricas()
        copia = {'portal_id': metricas['portal_id'], 'sessoes': metricas['aquisicao']['sessoes']['valor']}
        preparar_contexto(metricas, [], [])
        analisar(preparar_contexto(metricas, [], []))
        self.assertEqual(AnalyticsEvent.objects.count(), antes)
        self.assertEqual(metricas['portal_id'], copia['portal_id'])
        self.assertEqual(metricas['aquisicao']['sessoes']['valor'], copia['sessoes'])
        self.assertIn('email', metricas)

    def test_sem_cliente_nao_chama_api_e_nao_finge_analise(self):
        resposta = analisar(preparar_contexto(self._metricas(), [], []))
        self.assertFalse(resposta['disponivel'])
        self.assertEqual(resposta['motivo'], 'provedor_nao_configurado')
        self.assertIsNone(resposta['resumo'])
        self.assertEqual(resposta['observacoes'], [])

    def test_resposta_estruturada_e_aceita(self):
        recebido = {}

        def cliente(pacote):
            recebido['dados'] = pacote['dados']
            self.assertIn('instrucao', pacote)
            self.assertNotIn('e82198c9', str(pacote))
            return self._resposta()

        resposta = analisar(preparar_contexto(self._metricas(), [], []), cliente_ia=cliente)
        self.assertTrue(resposta['disponivel'])
        self.assertEqual(resposta['resumo'], 'Foi observada baixa passagem no funil gratuito.')
        self.assertEqual(len(resposta['hipoteses']), 1)
        self.assertEqual(recebido['dados']['portal_id'], 1)

    def test_resposta_invalida_causal_e_erro_do_provedor_sao_controlados(self):
        invalida = analisar({'periodo': 'hoje'}, cliente_ia=lambda pacote: 'texto livre')
        self.assertFalse(invalida['disponivel'])
        self.assertEqual(invalida['motivo'], 'resposta_invalida')
        causal = analisar({'periodo': 'hoje'}, cliente_ia=lambda pacote: self._resposta(
            resumo='O preço está causando abandono.',
        ))
        self.assertFalse(causal['disponivel'])
        self.assertEqual(causal['motivo'], 'resposta_invalida')

        def quebra(pacote):
            raise TimeoutError('provedor fora')

        falha = analisar({'periodo': 'hoje'}, cliente_ia=quebra)
        self.assertFalse(falha['disponivel'])
        self.assertEqual(falha['motivo'], 'provedor_indisponivel')
        self.assertIsNone(falha['resumo'])
        self.assertEqual(gerar({'funil_gratis': {'cliques': {'valor': 1}}}, []), [])

    def test_resposta_excessiva_e_rejeitada(self):
        resposta = analisar({'periodo': 'hoje'}, cliente_ia=lambda pacote: self._resposta(
            resumo='x' * 401,
        ))
        self.assertFalse(resposta['disponivel'])
        self.assertEqual(resposta['motivo'], 'resposta_excessiva')

    def test_isolamento_por_portal_no_contexto(self):
        a = preparar_contexto(self._metricas(portal_id=1, sessoes=247), [], [])
        b = preparar_contexto(self._metricas(portal_id=2, sessoes=3), [], [])
        self.assertEqual(a['portal_id'], 1)
        self.assertEqual(b['portal_id'], 2)
        self.assertEqual(a['metricas']['aquisicao']['sessoes']['valor'], 247)
        self.assertEqual(b['metricas']['aquisicao']['sessoes']['valor'], 3)
        self.assertNotIn('247', str(b))
