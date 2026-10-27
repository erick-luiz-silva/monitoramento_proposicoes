"""Carga do Senado Federal (docs/superpowers/specs/2026-10-27-senado-design.md).

Roda depois da Câmara, isolada dela: qualquer falha aqui vira aviso no e-mail e nunca
derruba a carga da Câmara (o orquestrador em extract_incremental/pipeline_pautas trata).
Ainda não habilitada: as funções são marcadores até a fase 3 do plano.
"""


def executar_carga_senado():
    print("Senado: carga ainda não habilitada.")


def executar_pautas_senado():
    print("Senado: carga de pautas ainda não habilitada.")
