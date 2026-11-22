"""Camada 4 — Rede (planejado, marco M4).

Problema de projeto de rede (network design) como MILP em Pyomo + HiGHS:
arcos candidatos = grafo de Gabriel/Delaunay entre cidades-polo; custo de cada arco vem do
greide ótimo (camada 3); benefício = horas economizadas × valor do tempo (camada 1).
Restrição de orçamento por fase (2035, 2045, 2060) → malha que cresce em etapas.
"""
