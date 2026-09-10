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

KEYWORDS = [
    ("suinocultura", r"\msuinocultura", None),
    ("suínos", r"\msuín", None),
    ("proteína animal", r"\mproteín.*\manima", None),
    ("rações animais", r"\mraç.*\manima", None),
    ("sanidade", r"\msanidade", None),
    ("animais de produção", r"\manima.*\mprodu", None),
    ("genética suína", r"\mgenétic.*\msuín", None),
    ("granjas", r"\mgranj", None),
    ("integração", r"\mintegraç", _CTX_AGRO),
    ("agroindústria", r"\magroindústr", None),
    ("animais de interesse econômico", r"\manima.*\minteresse.*\meconômic", None),
    ("avicultura", r"\mavicultura", None),
    ("aves", r"\mave", None),
    ("frango", r"\mfrang", None),
    ("milho", r"\mmilho", None),
    ("produtor rural", r"\mprodutor.*\mrura", None),
    ("trabalhador rural", r"\mtrabalhador.*\mrura", None),
    ("dejeto de animais", r"\mdejeto.*\manima", None),
    ("rótulo", r"\mrótul", None),
    ("gaiolas", r"\mgaiol", None),
    ("animais domésticos", r"\manima.*\mdoméstic", _CTX_PRODUCAO),
    ("bem-estar animal", r"\mbem.estar.*\manima", _CTX_PRODUCAO),
]
