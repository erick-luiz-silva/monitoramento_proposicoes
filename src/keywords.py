# Cada entrada é (rotulo, termo, termo_requerido).
#
# 'termo' é um fragmento de regex POSIX usado com o operador ~* do Postgres
# (case-insensitive). O prefixo \m ancora o INÍCIO de uma palavra: evita que um
# radical curto capture falsos positivos por estar embutido no meio de outra
# palavra (ex.: sem a âncora, o radical de "aves" bateria em "grave" e "Navega";
# o radical de "ração" bateria em "tração" e "castração").
#
# Termos com variação de gênero/número usam radical (ex.: "suín" cobre suíno,
# suína, suínos, suínas). Frases de duas palavras usam ".*" entre as âncoras
# para cobrir a concordância plural de ambas (ex.: "produtor rural" /
# "produtores rurais").
#
# 'termo_requerido' (None na maioria) é um 2º regex que TAMBÉM precisa bater na
# ementa ou no campo de keywords da Câmara para o termo contar. Serve para
# desambiguar termos genéricos que sozinhos trazem muito ruído.

# Contexto agroindustrial — "integração" só interessa no sentido de sistema de
# integração (agroindústria + produtor integrado), não "Ministério da Integração".
_CTX_AGRO = (
    r"(\magroindústr|\magroindustri|\mavicultura|\mavícol|\msuinocultura|\msuín|"
    r"\mgranj|\mabatedour|\mfrigorífic|produtor.*integrad|integrad.*produt)"
)

# Contexto de produção animal — separa bem-estar/animais "de produção" de
# bem-estar/animais "de companhia" (pet), cujo vocabulário é quase idêntico.
_CTX_PRODUCAO = (
    r"(\mabat|\mconfinament|\mgranj|\msuinocultura|\msuín|\mavicultura|\mavícol|"
    r"\mpecuár|\mrebanh|\mzootécni|\mfrigorífic|\mmatadour|cadeia produtiva|"
    r"animais de produção|animal de produção)"
)

def _ctx(*extras):
    """Estende o contexto de produção com alternativas extras (ex.: setor avícola)."""
    return "(" + "|".join([_CTX_PRODUCAO[1:-1], *extras]) + ")"


_CTX_AVES = _ctx(r"\mavicultur", r"\mavícol", r"\mfrang", r"\mpoedeir", r"\movos")
_CTX_TRABALHO_RURAL = _ctx(r"\msafr", r"\magropecuár", r"\magrícol")
_CTX_ORIGEM_ANIMAL = r"(origem animal|\mcarne|\mproteín|\mlátic|\membutid)"

KEYWORDS = [
    ("suinocultura", r"\msuinocultura", None),
    ("suínos", r"\msuín", None),
    ("proteína animal", r"\mproteín.*\manima", None),
    ("rações animais", r"\mraç.*\manima", _CTX_PRODUCAO),
    ("sanidade", r"\msanidade", None),
    ("animais de produção", r"\manima(is|l) de (produção|criação)|\mprodução animal", None),
    ("genética suína", r"\mgenétic.*\msuín", None),
    ("granjas", r"\mgranj", None),
    ("integração", r"\mintegraç", _CTX_AGRO),
    ("agroindústria", r"\magroindústr", None),
    ("animais de interesse econômico", r"\manima.*\minteresse.*\meconômic", None),
    ("avicultura", r"\mavicultura", None),
    ("aves", r"\mave", _CTX_AVES),
    ("frango", r"\mfrang", None),
    ("milho", r"\mmilho", _CTX_PRODUCAO),
    ("produtor rural", r"\mprodutor.*\mrura", None),
    ("trabalhador rural", r"\mtrabalhador.*\mrura", _CTX_TRABALHO_RURAL),
    ("dejeto de animais", r"\mdejeto.*\manima", None),
    ("rótulo", r"\mrótul|\mrotulag", _CTX_ORIGEM_ANIMAL),
    ("gaiolas", r"\mgaiol", None),
    ("animais domésticos", r"\manima.*\mdoméstic", _CTX_PRODUCAO),
    ("bem-estar animal", r"\mbem.estar.*\manima", _CTX_PRODUCAO),
]
