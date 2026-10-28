-- Fotografia única (15/10/2026) da planilha antiga de acompanhamento ("Acompanhamento manual"),
-- resolvida para ids da Câmara pelo comparar_acompanhamento.py. A planilha antiga fica só
-- para auditoria e não é lida por nenhuma automação. Idempotente: aplicada pelo setup_db.py.
-- Fora desta lista: PL 347/2003 (não localizada na API da Câmara; aguardando confirmação).
-- As proposições só do Senado da planilha antiga estão no fim (chave 1000000000 + id do Senado).
INSERT INTO silver.proposicao_acompanhada (id_proposicao, origem, observacao) VALUES
    (251853, 'planilha_antiga', 'PL 3479/2004'),
    (257161, 'planilha_antiga', 'PL 2159/2021'),
    (284989, 'planilha_antiga', 'PL 5194/2005'),
    (341067, 'planilha_antiga', 'PL 215/2007'),
    (495229, 'planilha_antiga', 'PL 767/2011'),
    (508884, 'planilha_antiga', 'PL 1572/2011'),
    (551686, 'planilha_antiga', 'PL 4195/2012'),
    (565397, 'planilha_antiga', 'PL 5010/2013'),
    (596099, 'planilha_antiga', 'PL 6559/2013'),
    (601739, 'planilha_antiga', 'PL 6054/2019'),
    (2054282, 'planilha_antiga', 'PL 3584/2015'),
    (2081331, 'planilha_antiga', 'PL 4905/2016'),
    (2086367, 'planilha_antiga', 'PL 5449/2016'),
    (2089026, 'planilha_antiga', 'PL 5651/2016'),
    (2092191, 'planilha_antiga', 'PL 5851/2016 (na planilha: PLC 10/2018)'),
    (2125913, 'planilha_antiga', 'PL 7155/2017'),
    (2148157, 'planilha_antiga', 'PL 8311/2017'),
    (2197747, 'planilha_antiga', 'PL 2237/2019'),
    (2203209, 'planilha_antiga', 'PL 2876/2019'),
    (2229763, 'planilha_antiga', 'PL 6028/2019'),
    (2262905, 'planilha_antiga', 'PL 4583/2020'),
    (2266883, 'planilha_antiga', 'PL 5498/2020'),
    (2266894, 'planilha_antiga', 'PL 5499/2020'),
    (2277190, 'planilha_antiga', 'PL 1293/2021'),
    (2278558, 'planilha_antiga', 'PL 1466/2021'),
    (2301103, 'planilha_antiga', 'PL 3384/2021'),
    (2306614, 'planilha_antiga', 'PL 3977/2021'),
    (2315041, 'planilha_antiga', 'PL 353/2022'),
    (2344901, 'planilha_antiga', 'PL 3047/2022 (na planilha: PLS 302/2018)'),
    (2346901, 'planilha_antiga', 'PL 173/2023'),
    (2349653, 'planilha_antiga', 'PL 752/2023'),
    (2351301, 'planilha_antiga', 'PL 1124/2023'),
    (2381605, 'planilha_antiga', 'RIC 2172/2023'),
    (2382103, 'planilha_antiga', 'PDL 277/2023'),
    (2397979, 'planilha_antiga', 'PL 5092/2023'),
    (2416887, 'planilha_antiga', 'PL 30/2024'),
    (2421307, 'planilha_antiga', 'PL 784/2024'),
    (2424280, 'planilha_antiga', 'PL 1045/2024'),
    (2433969, 'planilha_antiga', 'PL 1835/2024'),
    (2434960, 'planilha_antiga', 'PLP 95/2024'),
    (2436474, 'planilha_antiga', 'PL 2052/2024'),
    (2436763, 'planilha_antiga', 'PL 2098/2024'),
    (2446719, 'planilha_antiga', 'PL 2742/2024'),
    (2449119, 'planilha_antiga', 'PL 2881/2024'),
    (2467872, 'planilha_antiga', 'PL 4316/2024'),
    (2476518, 'planilha_antiga', 'PL 4717/2024'),
    (2487896, 'planilha_antiga', 'PL 1129/2025'),
    (2503337, 'planilha_antiga', 'PL 2047/2025'),
    (2518143, 'planilha_antiga', 'PL 2627/2025'),
    (2542405, 'planilha_antiga', 'PL 3895/2025'),
    (2553602, 'planilha_antiga', 'PL 4253/2025'),
    (2598974, 'planilha_antiga', 'PL 1167/2024'),
    (2641610, 'planilha_antiga', 'PL 4795/2026'),
    (2646587, 'planilha_antiga', 'PL 4262/2025')
ON CONFLICT (id_proposicao) DO NOTHING;

-- Proposições só do Senado da planilha antiga (chave = 1000000000 + id do processo no Senado,
-- config.SENADO_OFFSET). A MPV é acompanhada pelo Senado (decisão de 27/10/2026).
INSERT INTO silver.proposicao_acompanhada (id_proposicao, origem, observacao) VALUES
    (1008283772, 'planilha_antiga', 'PL 1879/2022 (Senado)'),
    (1008992504, 'planilha_antiga', 'PL 433/2026 (Senado)'),
    (1008900340, 'planilha_antiga', 'PL 4363/2025 (Senado)'),
    (1007376720, 'planilha_antiga', 'PLS 168/2018 (Senado)'),
    (1007403160, 'planilha_antiga', 'PLS 302/2018 (Senado)'),
    (1002913579, 'planilha_antiga', 'PLS 326/2016 (Senado)'),
    (1002916834, 'planilha_antiga', 'PLS 631/2015 (Senado)'),
    (1002916662, 'planilha_antiga', 'PLS 650/2015 (Senado)'),
    (1008537155, 'planilha_antiga', 'MPV 1186/2023 (Senado)')
ON CONFLICT (id_proposicao) DO NOTHING;

-- Versões do mesmo projeto que a API não liga (anotadas na planilha antiga):
-- PL 5851/2016 (Câmara) = PLC 10/2018 (Senado); PL 3047/2022 (Câmara) = PLS 302/2018 (Senado).
-- Sem FK: o processo do Senado pode ainda não estar na silver.
INSERT INTO silver.proposicao_vinculo (id_proposicao_cd, id_proposicao_sf, origem) VALUES
    (2092191, 1007364805, 'manual'),
    (2344901, 1007403160, 'manual')
ON CONFLICT (id_proposicao_cd, id_proposicao_sf) DO NOTHING;
