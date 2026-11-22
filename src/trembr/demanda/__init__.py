"""Camada 1 — Demanda (planejado, marco M1).

Método previsto:
1. Matriz OD observada: ANAC (passageiros por par de aeroportos) + ANTT (ônibus interestadual)
   + IBGE Ligações Rodoviárias; agregação por arranjo populacional (IBGE).
2. Modelo gravitacional estimado por PPML (Poisson pseudo-máxima verossimilhança; Santos Silva &
   Tenreyro, 2006), com população, PIB, distância/tempo generalizado e efeitos fixos de origem/destino.
3. Escolha modal logit multinomial (carro, ônibus, avião, trem) calibrada com elasticidades de
   literatura e validada por backtest em linhas reais (ex.: Madri–Barcelona, Pequim–Xangai).
"""
