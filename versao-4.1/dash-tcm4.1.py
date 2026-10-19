# --- Para executar este código, abra o terminal no PyCharm e digite:
# --- streamlit run dash-tcm4.1.py
# --- Para encerrar a execução: ctrl + c

from datetime import datetime
import itertools
import json
import os
import re
import time
import unicodedata
import pandas as pd
import pulp
import streamlit as st

# Configuração da página do Streamlit
st.set_page_config(
    layout="wide",
    page_title="TCM 4.1 - Prescrição Customizada & Otimização de Cadeiras de Rodas",
)

# Resolução dinâmica do diretório para execução robusta
DIRETORIO_SCRIPT = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_PRESC_SALVAS = os.path.join(
    DIRETORIO_SCRIPT, "dataset-prescricoes-manuais.json"
)

# Padrão inicial de pontuação técnica por fornecedor (idêntico à ETAPA 1 do Notebook)
PONTOS_QUALIDADE_PADRAO = {"Fornecedor-A": 3, "Fornecedor-B": 2, "Fornecedor-C": 1}

# Rótulos amigáveis de avaliação técnica
ROTULOS_PREFERENCIA = {
    3: "3 - Alta Preferência (1ª Opção / Fornecedor-A)",
    2: "2 - Preferência Média (2ª Opção / Fornecedor-B)",
    1: "1 - Opção Básica (3ª Opção / Fornecedor-C)",
}

# ==========================================
# FUNÇÕES DE FORMATAÇÃO E NORMALIZAÇÃO
# ==========================================
def formatar_moeda(valor):
    if pd.isna(valor) or valor is None:
        return "R$ 0,00"
    return (
        f"R$ {float(valor):,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def normalizar_texto(texto):
    if not texto:
        return ""
    texto = str(texto).lower()
    return "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    ).strip()


def formatar_inteiro(valor):
    if pd.isna(valor) or valor is None:
        return "0"
    return f"{int(valor):,}".replace(",", ".")


def reiniciar_formulario_nova_prescricao():
    """Limpa as seleções e força a recriação dos campos com novo estado."""
    if "form_version" not in st.session_state:
        st.session_state["form_version"] = 0
    st.session_state["form_version"] += 1

    # Remove chaves de estado de sessões anteriores
    for k in list(st.session_state.keys()):
        if k.startswith("qual_") or k.startswith("txt_"):
            del st.session_state[k]

    st.session_state["aba_ativa"] = "📝 Nova Prescrição & Otimização"
    st.rerun()


# ==========================================
# CARGA DO CATÁLOGO DE COMPONENTES
# ==========================================
@st.cache_data
def carregar_catalogo():
    path_ds7 = os.path.join(DIRETORIO_SCRIPT, "dataset_7_componentes.json")
    if not os.path.exists(path_ds7):
        path_ds7 = "dataset_7_componentes.json"

    if not os.path.exists(path_ds7):
        st.error(
            "Arquivo 'dataset_7_componentes.json' não encontrado nem em"
            f" '{DIRETORIO_SCRIPT}' nem na raiz."
        )
        st.stop()

    with open(path_ds7, "r", encoding="utf-8") as f:
        ds7 = json.load(f)

    catmat_dict = {}
    descricoes_oficiais = {}
    categorias_dict = {}
    todos_fornecedores = set()

    for comp in ds7["componentes"]:
        id_comp = comp["id_componente"]
        forn = comp["fornecedor"]
        preco = float(comp.get("preco_max_BRL", 0))
        todos_fornecedores.add(forn)

        if id_comp not in catmat_dict:
            catmat_dict[id_comp] = {}
            descricoes_oficiais[id_comp] = comp.get("descricao_oficial", "")
            categorias_dict[id_comp] = comp.get("categoria", "Outros")
        catmat_dict[id_comp][forn] = preco

    return (
        catmat_dict,
        descricoes_oficiais,
        categorias_dict,
        sorted(list(todos_fornecedores)),
    )


(
    catmat_dict,
    descricoes_oficiais,
    categorias_dict,
    lista_fornecedores_catalogo,
) = carregar_catalogo()


# ==========================================
# ALGORITMO DE MAPEAMENTO DINÂMICO
# ==========================================
def mapear_termo_dinamico(termo, descricoes_dict):
    """Replica a busca exata e a sobreposição de tokens (>= 90%) desenvolvida na
    ETAPA 3 do notebook.
    """
    termo_norm = normalizar_texto(termo)
    if not termo_norm:
        return None

    termo_tokens = set(termo_norm.split())

    # Tentativa 1: Busca Exata (termo contido no ID ou na descrição do catálogo)
    for id_catalogo, desc_oficial in descricoes_dict.items():
        if termo_norm in normalizar_texto(
            id_catalogo
        ) or termo_norm in normalizar_texto(desc_oficial):
            return id_catalogo

    # Tentativa 2: Similaridade por Intersecção de Tokens (critério >= 90%)
    melhor_match = None
    maior_sobreposicao = 0
    total_tokens = len(termo_tokens)

    for id_catalogo, desc_oficial in descricoes_dict.items():
        desc_tokens = set(normalizar_texto(desc_oficial).split())
        sobreposicao = len(termo_tokens.intersection(desc_tokens))

        if sobreposicao > maior_sobreposicao and sobreposicao >= (
            total_tokens * 0.90
        ):
            maior_sobreposicao = sobreposicao
            melhor_match = id_catalogo

    return melhor_match


# ==========================================
# PERSISTÊNCIA DE PRESCRIÇÕES
# ==========================================
def carregar_prescricoes_salvas():
    if not os.path.exists(ARQUIVO_PRESC_SALVAS):
        return []
    try:
        with open(ARQUIVO_PRESC_SALVAS, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def obter_proximo_identificador_paciente():
    prescricoes = carregar_prescricoes_salvas()
    numeros = []
    padrao = re.compile(r"^paciente#m?(\d+)$", re.IGNORECASE)

    for p in prescricoes:
        nome = p.get("nome_paciente", "").strip()
        match = padrao.match(nome)
        if match:
            numeros.append(int(match.group(1)))

    if not numeros:
        proximo_num = 1
    else:
        proximo_num = max(numeros) + 1

    return f"Paciente#{proximo_num:04d}"


def existe_paciente_na_base(identificador_paciente, id_ignorar=None):
    prescricoes = carregar_prescricoes_salvas()
    id_procurado = identificador_paciente.strip().lower()
    for p in prescricoes:
        if id_ignorar and p.get("id_prescricao") == id_ignorar:
            continue
        if p.get("nome_paciente", "").strip().lower() == id_procurado:
            return True
    return False


def salvar_nova_prescricao(
    id_prescricao,
    nome_paciente,
    termos_prescritos,
    itens_ids,
    lambda_val,
    orcamento_val,
    status_plim,
    custo_plim,
    qual_plim,
    fo_plim,
    df_det_plim,
    status_fb,
    custo_fb,
    qual_fb,
    fo_fb,
    df_det_fb,
    tempo_plim,
    tempo_fb,
    total_comb_fb,
    mapa_qualidade_item,
):
    prescricoes = carregar_prescricoes_salvas()
    registro = {
        "id_prescricao": id_prescricao,
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nome_paciente": nome_paciente,
        "termos_originais": termos_prescritos,
        "itens_prescritos": itens_ids,
        "total_itens": len(itens_ids),
        "lambda": lambda_val,
        "limite_orcamento": orcamento_val,
        "status_otimizacao": status_plim,
        "custo_total": custo_plim,
        "qualidade_total": qual_plim,
        "valor_fo": fo_plim,
        "tempo_plim": tempo_plim,
        "status_fb": status_fb,
        "custo_fb": custo_fb,
        "qualidade_fb": qual_fb,
        "valor_fo_fb": fo_fb,
        "tempo_fb": tempo_fb,
        "total_comb_fb": total_comb_fb,
        "mapa_qualidade_item": mapa_qualidade_item,
        "detalhes_plim": df_det_plim.to_dict(orient="records"),
        "detalhes_fb": (
            df_det_fb.to_dict(orient="records") if df_det_fb is not None and not df_det_fb.empty else []
        ),
    }
    prescricoes = [p for p in prescricoes if p["id_prescricao"] != id_prescricao]
    prescricoes.insert(0, registro)
    with open(ARQUIVO_PRESC_SALVAS, "w", encoding="utf-8") as f:
        json.dump(prescricoes, f, ensure_ascii=False, indent=2)


def atualizar_prescricao_existente(
    id_prescricao,
    novo_nome_paciente,
    novos_termos_prescritos,
    novos_itens_ids,
    lambda_val,
    orcamento_val,
    status_plim,
    custo_plim,
    qual_plim,
    fo_plim,
    df_det_plim,
    status_fb,
    custo_fb,
    qual_fb,
    fo_fb,
    df_det_fb,
    tempo_plim,
    tempo_fb,
    total_comb_fb,
    mapa_qualidade_item,
):
    prescricoes = carregar_prescricoes_salvas()
    for p in prescricoes:
        if p["id_prescricao"] == id_prescricao:
            p["data_hora_atualizacao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            p["nome_paciente"] = novo_nome_paciente
            p["termos_originais"] = novos_termos_prescritos
            p["itens_prescritos"] = novos_itens_ids
            p["total_itens"] = len(novos_itens_ids)
            p["lambda"] = lambda_val
            p["limite_orcamento"] = orcamento_val
            p["status_otimizacao"] = status_plim
            p["custo_total"] = custo_plim
            p["qualidade_total"] = qual_plim
            p["valor_fo"] = fo_plim
            p["tempo_plim"] = tempo_plim
            p["status_fb"] = status_fb
            p["custo_fb"] = custo_fb
            p["qualidade_fb"] = qual_fb
            p["valor_fo_fb"] = fo_fb
            p["tempo_fb"] = tempo_fb
            p["total_comb_fb"] = total_comb_fb
            p["mapa_qualidade_item"] = mapa_qualidade_item
            p["detalhes_plim"] = df_det_plim.to_dict(orient="records")
            p["detalhes_fb"] = (
                df_det_fb.to_dict(orient="records") if df_det_fb is not None and not df_det_fb.empty else []
            )
            break

    with open(ARQUIVO_PRESC_SALVAS, "w", encoding="utf-8") as f:
        json.dump(prescricoes, f, ensure_ascii=False, indent=2)


def excluir_prescricao_salva(id_prescricao):
    prescricoes = carregar_prescricoes_salvas()
    prescricoes = [p for p in prescricoes if p["id_prescricao"] != id_prescricao]
    with open(ARQUIVO_PRESC_SALVAS, "w", encoding="utf-8") as f:
        json.dump(prescricoes, f, ensure_ascii=False, indent=2)


# ==========================================
# MOTORES DE OTIMIZAÇÃO (PLIM E FORÇA BRUTA)
# ==========================================
def resolver_plim(
    itens_prescritos, lambda_param, limite_orcamento, mapa_qualidade
):
    itens_validos = [k for k in itens_prescritos if k in catmat_dict]
    if not itens_validos:
        return "Inviável - Itens ausentes", 0.0, 0.0, None, pd.DataFrame(), 0.0

    t0 = time.time()
    n_itens = len(itens_validos)
    custo_max_poss = float(
        sum(max(catmat_dict[k].values()) for k in itens_validos)
    )

    qual_max_poss = float(
        sum(
            max(mapa_qualidade.get(k, {}).values(), default=3.0)
            for k in itens_validos
        )
    )
    if qual_max_poss <= 0:
        qual_max_poss = float(n_itens * 3.0)

    m = pulp.LpProblem("PLIM_Customizado", pulp.LpMinimize)

    x = {}
    for idx, k in enumerate(itens_validos):
        for f in catmat_dict[k].keys():
            var_name = f"x_{idx}_{k}_{f}".replace("-", "_").replace(" ", "_")
            x[(idx, k, f)] = pulp.LpVariable(var_name, cat=pulp.LpBinary)

    custo_total = pulp.lpSum(
        x[idx, k, f] * float(catmat_dict[k][f])
        for idx, k in enumerate(itens_validos)
        for f in catmat_dict[k].keys()
    )

    qualidade_total = pulp.lpSum(
        x[idx, k, f] * float(mapa_qualidade.get(k, {}).get(f, 1))
        for idx, k in enumerate(itens_validos)
        for f in catmat_dict[k].keys()
    )

    f_custo = (
        (float(lambda_param) / custo_max_poss)
        if custo_max_poss > 0
        else float(lambda_param)
    )
    f_qual = (
        (float(1.0 - lambda_param) / qual_max_poss)
        if qual_max_poss > 0
        else float(1.0 - lambda_param)
    )

    m += (f_custo * custo_total) - (f_qual * qualidade_total)

    for idx, k in enumerate(itens_validos):
        m += pulp.lpSum(x[idx, k, f] for f in catmat_dict[k].keys()) == 1

    m += custo_total <= float(limite_orcamento)

    m.solve(pulp.PULP_CBC_CMD(msg=0))
    tempo_exec = time.time() - t0

    detalhes = []
    if pulp.LpStatus[m.status] == "Optimal":
        status = "Solução Otimizada (Dentro do Orçamento)"
        custo = float(pulp.value(custo_total))
        qualidade = float(pulp.value(qualidade_total))
        fo = float(pulp.value(m.objective))
        for idx, k in enumerate(itens_validos):
            for f in catmat_dict[k].keys():
                if round(pulp.value(x[idx, k, f])) == 1:
                    nota_f = mapa_qualidade.get(k, {}).get(f, 1)
                    detalhes.append({
                        "Componente": k,
                        "Fornecedor Selecionado": f,
                        "Valor Unitário (R$)": catmat_dict[k][f],
                        "Pontos de Adequação Técnica": nota_f,
                    })
    else:
        status = f"Excedeu {formatar_moeda(limite_orcamento)}"
        custo = 0.0
        qualidade = 0.0
        fo = None
        for k in itens_validos:
            f_min = min(catmat_dict[k], key=lambda f: catmat_dict[k][f])
            custo += catmat_dict[k][f_min]
            qualidade += mapa_qualidade.get(k, {}).get(f_min, 1)
            detalhes.append({
                "Componente": k,
                "Fornecedor Selecionado": f_min,
                "Valor Unitário (R$)": catmat_dict[k][f_min],
                "Pontos de Adequação Técnica": mapa_qualidade.get(k, {}).get(
                    f_min, 1
                ),
            })

    return status, custo, qualidade, fo, pd.DataFrame(detalhes), tempo_exec


def resolver_forca_bruta(
    itens_prescritos, lambda_param, limite_orcamento, mapa_qualidade
):
    itens_validos = [k for k in itens_prescritos if k in catmat_dict]
    if not itens_validos:
        return (
            "Inviável - Itens ausentes",
            0.0,
            0.0,
            None,
            pd.DataFrame(),
            0,
            0.0,
            "0 = 0",
        )

    t0 = time.time()
    n_itens = len(itens_validos)
    custo_max_poss = float(
        sum(max(catmat_dict[k].values()) for k in itens_validos)
    )

    qual_max_poss = float(
        sum(
            max(mapa_qualidade.get(k, {}).values(), default=3.0)
            for k in itens_validos
        )
    )
    if qual_max_poss <= 0:
        qual_max_poss = float(n_itens * 3.0)

    opcoes_fornecedores = [list(catmat_dict[k].keys()) for k in itens_validos]

    total_combinacoes = 1
    for op in opcoes_fornecedores:
        total_combinacoes *= len(op)

    if total_combinacoes > 60000:
        return (
            "Busca Exaustiva Ignorada (Espaço Combinatório > 60.000)",
            0.0,
            0.0,
            None,
            pd.DataFrame(),
            total_combinacoes,
            0.0,
            f"Espaço: {formatar_inteiro(total_combinacoes)} combinações (Executado apenas via PLIM)",
        )

    melhor_fo = float("inf")
    melhor_comb = None
    melhor_custo = 0.0
    melhor_qual = 0.0

    for comb in itertools.product(*opcoes_fornecedores):
        custo_comb = sum(catmat_dict[k][f] for k, f in zip(itens_validos, comb))
        if custo_comb <= limite_orcamento:
            qual_comb = sum(
                mapa_qualidade.get(k, {}).get(f, 1) for k, f in zip(itens_validos, comb)
            )
            c_norm = (
                (custo_comb / custo_max_poss) if custo_max_poss > 0 else custo_comb
            )
            q_norm = (
                (qual_comb / qual_max_poss) if qual_max_poss > 0 else qual_comb
            )
            fo_comb = (lambda_param * c_norm) - ((1.0 - lambda_param) * q_norm)

            if fo_comb < melhor_fo:
                melhor_fo = fo_comb
                melhor_comb = comb
                melhor_custo = custo_comb
                melhor_qual = qual_comb

    detalhes = []
    if melhor_comb is not None:
        status = "Solução Otimizada (Dentro do Orçamento)"
        for k, f in zip(itens_validos, melhor_comb):
            detalhes.append({
                "Componente": k,
                "Fornecedor Selecionado": f,
                "Valor Unitário (R$)": catmat_dict[k][f],
                "Pontos de Adequação Técnica": mapa_qualidade.get(k, {}).get(f, 1),
            })
    else:
        status = f"Excedeu {formatar_moeda(limite_orcamento)}"
        melhor_custo = 0.0
        melhor_qual = 0.0
        melhor_fo = None
        for k in itens_validos:
            f_min = min(catmat_dict[k], key=lambda f: catmat_dict[k][f])
            melhor_custo += catmat_dict[k][f_min]
            melhor_qual += mapa_qualidade.get(k, {}).get(f_min, 1)
            detalhes.append({
                "Componente": k,
                "Fornecedor Selecionado": f_min,
                "Valor Unitário (R$)": catmat_dict[k][f_min],
                "Pontos de Adequação Técnica": mapa_qualidade.get(k, {}).get(
                    f_min, 1
                ),
            })

    tempo_exec = time.time() - t0
    racional_calculo = (
        " × ".join([str(len(op)) for op in opcoes_fornecedores])
        + f" = {formatar_inteiro(total_combinacoes)}"
    )

    return (
        status,
        melhor_custo,
        melhor_qual,
        melhor_fo,
        pd.DataFrame(detalhes),
        total_combinacoes,
        tempo_exec,
        racional_calculo,
    )


# ==========================================
# INTERFACE STREAMLIT (UI)
# ==========================================
st.title("♿ TCM 4.1 - Otimização de Prescrições Clínicas")
st.markdown(
    "Sistema de apoio à decisão para customização de cadeiras de rodas"
    " personalizadas. Aplica o algoritmo de **Mapeamento Textual Dinâmico"
    r" (Similaridade de Tokens $\ge 90\%$)"
    "** e o **Solver PLIM (PuLP)** com auditoria comparativa direta lado a lado contra a **Busca Exaustiva (Força Bruta)**."
)

# ----------------------------------------------------
# BARRA LATERAL (DIRETRIZES DE DECISÃO PADRÃO)
# ----------------------------------------------------
st.sidebar.header("⚖️ Diretrizes de Decisão (Geral)")

LAMBDA = st.sidebar.slider(
    "Fator de Ponderação (λ) - Custo vs. Qualidade:",
    0.0,
    1.0,
    0.2,
    0.1,
    help=(
        "λ = 0.2 prioriza 80% qualidade técnica e 20% redução de custos (padrão"
        " do estudo)."
    ),
)

perc_economia = int(round(LAMBDA * 100))
perc_qualidade = int(round((1 - LAMBDA) * 100))

col_p1, col_p2 = st.sidebar.columns(2)
col_p1.metric("Prioridade Técnica", f"{perc_qualidade}%")
col_p2.metric("Foco Econômico", f"{perc_economia}%")

LIMITE_ORCAMENTO = st.sidebar.number_input(
    "Teto Orçamentário Disponível (R$):",
    min_value=500.0,
    value=10000.0,
    step=500.0,
    help="Teto máximo de gastos autorizado por paciente (Padrão: R$ 10.000,00).",
)

# ----------------------------------------------------
# CONTROLE DE ESTADO DA GUIA ATIVA
# (Evita que a tela pule de guia ao mexer em sliders ou inputs)
# ----------------------------------------------------
opcoes_guias = [
    "📝 Nova Prescrição & Otimização",
    "📂 Histórico de Prescrições Salvas",
]

if "aba_ativa" not in st.session_state:
    st.session_state["aba_ativa"] = opcoes_guias[0]

aba_selecionada = st.radio(
    "Navegação:",
    opcoes_guias,
    index=opcoes_guias.index(st.session_state["aba_ativa"]),
    horizontal=True,
    label_visibility="collapsed",
)

# Mantém a aba ativa consistente na sessão
st.session_state["aba_ativa"] = aba_selecionada

# ----------------------------------------------------
# GUIA 1: NOVA PRESCRIÇÃO & OTIMIZAÇÃO DINÂMICA
# ----------------------------------------------------
if aba_selecionada == "📝 Nova Prescrição & Otimização":
    if "form_version" not in st.session_state:
        st.session_state["form_version"] = 0
    v = st.session_state["form_version"]

    col_topo_btn, _ = st.columns([1, 3])
    with col_topo_btn:
        if st.button(
            "➕ Incluir Nova Prescrição",
            key=f"btn_nova_topo_{v}",
            help="Limpa todas as escolhas para iniciar uma nova prescrição",
        ):
            reiniciar_formulario_nova_prescricao()

    st.markdown("---")

    col_id1, col_id2 = st.columns([1, 1])
    id_sugestao = f"PRESC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    paciente_sugestao = obter_proximo_identificador_paciente()

    with col_id1:
        id_prescricao_input = st.text_input(
            "Código de Identificação da Prescrição (Automático):",
            value=id_sugestao,
            disabled=True,
            key=f"id_presc_{v}",
        )
    with col_id2:
        nome_paciente_input = st.text_input(
            "Identificador / Nome do Paciente:",
            value=paciente_sugestao,
            key=f"nome_pac_{v}",
            help="Identificador anônimo sequencial sugerido pelo sistema.",
        )

    st.info(
        "💡 Selecione o modelo base do chassi (opcional) e insira a lista de componentes"
        " prescritos (um por linha)."
    )

    # Inicia vazio por padrão (index=None) e pode ser deixado em branco
    modelo_cadeira = st.selectbox(
        "Estrutura / Modelo da Cadeira (Chassi):",
        ["RELAX", "PRISMA"],
        index=None,
        placeholder="Selecione um chassi (ou deixe em branco)...",
        key=f"txt_mod_cad_{v}",
    )

    itens_inclusos_txt = st.text_area(
        "Itens Inclusos e Componentes Prescritos (um por linha):",
        placeholder=(
            "Exemplo:\nAssento anatômico com onda\nApoio de braços\nCinto"
            " peitoral\nApoio de quadril\nApoio de cabeça occipital"
        ),
        height=280,
        key=f"txt_inclusos_{v}",
    )

    termos_brutos_prescritos = []

    if modelo_cadeira is not None and modelo_cadeira.strip():
        termos_brutos_prescritos.append(modelo_cadeira.strip())

    for linha in itens_inclusos_txt.split("\n"):
        t = linha.strip()
        if t:
            termos_brutos_prescritos.append(t)

    # ====================================================
    # MAPEAMENTO TEXTUAL DINÂMICO
    # ====================================================
    itens_mapeados_ids = []
    itens_nao_encontrados = []
    tabela_mapeamento = []

    for termo in termos_brutos_prescritos:
        if termo in catmat_dict:
            id_cat = termo
            itens_mapeados_ids.append(id_cat)
            tabela_mapeamento.append({
                "Termo Prescrito": termo,
                "ID Catálogo Encontrado": id_cat,
                "Descrição Oficial": descricoes_oficiais.get(id_cat, ""),
                "Método": "Código Direto",
            })
        else:
            id_cat = mapear_termo_dinamico(termo, descricoes_oficiais)
            if id_cat:
                itens_mapeados_ids.append(id_cat)
                tabela_mapeamento.append({
                    "Termo Prescrito": termo,
                    "ID Catálogo Encontrado": id_cat,
                    "Descrição Oficial": descricoes_oficiais.get(id_cat, ""),
                    "Método": "Similaridade Dinâmica (≥ 90%)",
                })
            else:
                itens_nao_encontrados.append(termo)
                tabela_mapeamento.append({
                    "Termo Prescrito": termo,
                    "ID Catálogo Encontrado": "NÃO ENCONTRADO",
                    "Descrição Oficial": (
                        "Nenhum componente atingiu o limiar de 90% de sobreposição"
                    ),
                    "Método": "Falha de Mapeamento",
                })

    itens_validos_unicos = list(dict.fromkeys(itens_mapeados_ids))

    st.divider()
    st.subheader(
        f"🔍 Auditoria de Mapeamento Clínico ({len(termos_brutos_prescritos)}"
        " termos)"
    )

    if termos_brutos_prescritos:
        df_mapa_view = pd.DataFrame(tabela_mapeamento)
        st.dataframe(df_mapa_view, use_container_width=True)

        if itens_nao_encontrados:
            st.error(
                "❌ **Restrição Hard Violada:** Os seguintes termos prescritos não"
                f" foram mapeados no catálogo: {', '.join(itens_nao_encontrados)}. O"
                " modelo requer 100% dos itens mapeados para garantir viabilidade."
            )
        else:
            st.success(
                "✅ 100% dos itens prescritos foram mapeados com sucesso no catálogo"
                " oficial!"
            )
    else:
        st.info("Insira os termos da prescrição acima para processar o mapeamento.")

    st.divider()

    # ====================================================
    # AVALIAÇÃO DE PREFERÊNCIA TÉCNICA (1, 2 OU 3 SEM REPETIÇÃO)
    # ====================================================
    st.subheader("🎖️ Ordem de Preferência Técnica dos Fornecedores por Item")
    st.markdown(
        "Para cada componente, classifique os fornecedores em **1ª Opção (3)**, **2ª Opção (2)** e **3ª Opção (1)**. "
        "**Atenção:** As notas não podem se repetir para o mesmo componente."
    )

    mapa_qualidade_coletado = {}
    erro_notas_duplicadas = False
    componentes_com_erro = []

    if itens_validos_unicos and not itens_nao_encontrados:
        for cod_item in itens_validos_unicos:
            desc_item = descricoes_oficiais.get(cod_item, "Sem descrição")
            cat_item = categorias_dict.get(cod_item, "Outros")
            fornecedores_item = list(catmat_dict.get(cod_item, {}).keys())

            with st.expander(
                f"📦 [{cat_item}] {cod_item} - {desc_item[:70]}...", expanded=True
            ):
                st.caption(f"**Descrição Técnica:** {desc_item}")
                cols_forn = st.columns(len(fornecedores_item))
                notas_item = {}

                for idx_f, forn in enumerate(fornecedores_item):
                    preco_ref = catmat_dict[cod_item][forn]
                    val_def = PONTOS_QUALIDADE_PADRAO.get(forn, max(1, 3 - idx_f))

                    with cols_forn[idx_f]:
                        st.markdown(f"**{forn}**")
                        st.markdown(f"Preço: `{formatar_moeda(preco_ref)}`")
                        nota = st.selectbox(
                            f"Avaliação ({forn}):",
                            options=[3, 2, 1],
                            index=[3, 2, 1].index(val_def) if val_def in [3, 2, 1] else 0,
                            format_func=lambda x: ROTULOS_PREFERENCIA.get(x, str(x)),
                            key=f"qual_{v}_{cod_item}_{forn}",
                        )
                        notas_item[forn] = int(nota)

                valores_notas_item = list(notas_item.values())
                if len(valores_notas_item) != len(set(valores_notas_item)):
                    st.error(
                        f"⚠️ **Ajuste de preferência em {cod_item}:** Foram atribuídas opções repetidas. "
                        "Por favor, ordene os fornecedores em 1ª (3), 2ª (2) e 3ª (1) opção sem repetir notas no mesmo item."
                    )
                    erro_notas_duplicadas = True
                    componentes_com_erro.append(cod_item)

                mapa_qualidade_coletado[cod_item] = notas_item

    # BOTÕES DE AÇÃO NO FINAL DA TELA
    col_salvar, col_fim_btn = st.columns([2, 1])

    with col_salvar:
        btn_calcular = st.button(
            "🚀 Executar Solver PLIM e Salvar Prescrição",
            type="primary",
            key=f"btn_calc_{v}",
        )

    with col_fim_btn:
        if st.button(
            "➕ Incluir Nova Prescrição",
            key=f"btn_nova_fim_{v}",
            help="Limpa todas as escolhas para iniciar uma nova prescrição",
        ):
            reiniciar_formulario_nova_prescricao()

    if btn_calcular:
        nome_paciente_final = nome_paciente_input.strip()

        if not nome_paciente_final:
            st.error("Por favor, preencha o campo com a identificação do paciente.")
            st.stop()

        if not termos_brutos_prescritos:
            st.error(
                "Por favor, insira os componentes da prescrição antes de executar."
            )
            st.stop()

        if itens_nao_encontrados:
            st.error(
                "❌ Não é possível executar a otimização com itens não mapeados:"
                f" {', '.join(itens_nao_encontrados)}."
            )
            st.stop()

        if erro_notas_duplicadas:
            st.error(
                f"❌ Identificamos preferências repetidas nos seguintes componentes: {', '.join(componentes_com_erro)}. "
                "Distribua as posições (1ª, 2ª e 3ª) de forma exclusiva em cada um antes de prosseguir."
            )
            st.stop()

        if existe_paciente_na_base(nome_paciente_final):
            st.error(
                f"O identificador '{nome_paciente_final}' já existe nos registros."
                " Use outro identificador."
            )
            st.stop()

        with st.spinner(
            "Processando o modelo PLIM e auditando espaço de soluções..."
        ):
            status_plim, custo_plim, qual_plim, fo_plim, df_det_plim, tempo_plim = resolver_plim(
                itens_validos_unicos,
                LAMBDA,
                LIMITE_ORCAMENTO,
                mapa_qualidade_coletado,
            )

            (
                status_fb,
                custo_fb,
                qual_fb,
                fo_fb,
                df_det_fb,
                total_comb_fb,
                tempo_fb,
                racional_espaco,
            ) = resolver_forca_bruta(
                itens_validos_unicos,
                LAMBDA,
                LIMITE_ORCAMENTO,
                mapa_qualidade_coletado,
            )

            salvar_nova_prescricao(
                id_prescricao=id_prescricao_input,
                nome_paciente=nome_paciente_final,
                termos_prescritos=termos_brutos_prescritos,
                itens_ids=itens_validos_unicos,
                lambda_val=LAMBDA,
                orcamento_val=LIMITE_ORCAMENTO,
                status_plim=status_plim,
                custo_plim=custo_plim,
                qual_plim=qual_plim,
                fo_plim=fo_plim,
                df_det_plim=df_det_plim,
                status_fb=status_fb,
                custo_fb=custo_fb,
                qual_fb=qual_fb,
                fo_fb=fo_fb,
                df_det_fb=df_det_fb,
                tempo_plim=tempo_plim,
                tempo_fb=tempo_fb,
                total_comb_fb=total_comb_fb,
                mapa_qualidade_item=mapa_qualidade_coletado,
            )

        st.success(
            f"Prescrição {id_prescricao_input} ({nome_paciente_final}) calculada e"
            " armazenada com sucesso."
        )

        st.header("📊 Comparativo dos Resultados: Solver PLIM (CBC) vs. Força Bruta")
        st.caption(f"Espaço Amostral Auditado: `{formatar_inteiro(total_comb_fb)}` combinações possíveis ({racional_espaco}).")

        max_qual_teorica = len(itens_validos_unicos) * 3

        # Exibição LADO A LADO das métricas
        col_res_plim, col_res_fb = st.columns(2)

        with col_res_plim:
            st.subheader("⚙️ Solver PLIM (CBC)")
            st.metric("Situação", status_plim)
            st.metric("Valor Total da Cadeira", formatar_moeda(custo_plim), f"Teto: {formatar_moeda(LIMITE_ORCAMENTO)}")
            st.metric("Nível de Adequação Técnica", f"{qual_plim:.0f} pts", f"Máx: {max_qual_teorica:.0f} pts")
            fo_plim_str = f"{fo_plim:.4f}" if fo_plim is not None else "N/A"
            st.metric("Valor da Função Objetivo (FO)", fo_plim_str)
            st.metric("Tempo de Processamento", f"{tempo_plim:.4f} s")

        with col_res_fb:
            st.subheader("🔍 Força Bruta (Busca Exaustiva)")
            st.metric("Situação", status_fb)
            st.metric("Valor Total da Cadeira", formatar_moeda(custo_fb), f"Teto: {formatar_moeda(LIMITE_ORCAMENTO)}")
            st.metric("Nível de Adequação Técnica", f"{qual_fb:.0f} pts", f"Máx: {max_qual_teorica:.0f} pts")
            fo_fb_str = f"{fo_fb:.4f}" if fo_fb is not None else "N/A"
            st.metric("Valor da Função Objetivo (FO)", fo_fb_str)
            st.metric("Tempo de Processamento", f"{tempo_fb:.4f} s")

        st.divider()

        # Exibição LADO A LADO das tabelas detalhadas
        st.subheader("📋 Composição e Fornecedores Selecionados (Lado a Lado)")
        col_tab_plim, col_tab_fb = st.columns(2)

        with col_tab_plim:
            st.markdown("**Composição Aprovada pelo Solver PLIM (CBC)**")
            if not df_det_plim.empty:
                st.dataframe(
                    df_det_plim.style.format({
                        "Valor Unitário (R$)": formatar_moeda,
                        "Pontos de Adequação Técnica": "{:.0f}",
                    }),
                    use_container_width=True,
                )
            else:
                st.info("Nenhum dado gerado pelo Solver PLIM.")

        with col_tab_fb:
            st.markdown("**Composição Aprovada pela Força Bruta**")
            if not df_det_fb.empty:
                st.dataframe(
                    df_det_fb.style.format({
                        "Valor Unitário (R$)": formatar_moeda,
                        "Pontos de Adequação Técnica": "{:.0f}",
                    }),
                    use_container_width=True,
                )
            else:
                st.warning("Busca Exaustiva não executada para este espaço amostral.")

# ----------------------------------------------------
# GUIA 2: HISTÓRICO DE PRESCRIÇÕES SALVAS & EDIÇÃO
# ----------------------------------------------------
else:
    st.header("📂 Gerenciamento de Prescrições (Consultar / Alterar / Excluir)")

    # Exibição persistente da notificação de alteração bem-sucedida
    if "msg_sucesso_edicao" in st.session_state:
        st.success(st.session_state["msg_sucesso_edicao"])
        del st.session_state["msg_sucesso_edicao"]

    historico = carregar_prescricoes_salvas()

    if not historico:
        st.info("Nenhuma prescrição cadastrada até o momento.")
    else:
        df_hist = pd.DataFrame(historico)
        colunas_exibir = [
            "id_prescricao",
            "data_hora",
            "nome_paciente",
            "total_itens",
            "status_otimizacao",
            "custo_total",
            "qualidade_total",
            "valor_fo",
            "lambda",
            "limite_orcamento",
        ]

        for c in colunas_exibir:
            if c not in df_hist.columns:
                df_hist[c] = None

        df_hist_vis = df_hist[colunas_exibir].rename(
            columns={
                "id_prescricao": "ID Prescrição",
                "data_hora": "Data/Hora",
                "nome_paciente": "Paciente / Identificador",
                "total_itens": "Qtd. Itens",
                "status_otimizacao": "Situação",
                "custo_total": "Valor Total",
                "qualidade_total": "Adequação Técnica",
                "valor_fo": "Índice Custo-Benefício (FO)",
                "lambda": "Fator λ",
                "limite_orcamento": "Teto Orçamentário",
            }
        )

        st.dataframe(
            df_hist_vis.style.format({
                "Valor Total": formatar_moeda,
                "Teto Orçamentário": formatar_moeda,
                "Adequação Técnica": "{:.0f} pts",
                "Índice Custo-Benefício (FO)": (
                    lambda x: f"{x:.4f}" if pd.notna(x) else "N/A"
                ),
                "Fator λ": "{:.2f}",
            }),
            use_container_width=True,
        )

        json_bytes = json.dumps(historico, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        st.download_button(
            label="📥 Exportar Base Completa em JSON",
            data=json_bytes,
            file_name="dataset-prescricoes-manuais.json",
            mime="application/json",
        )

        st.divider()
        st.subheader("🛠️ Detalhes e Ajustes da Prescrição")

        opcoes_presc = [
            f"{p['id_prescricao']} | {p['nome_paciente']} ({p['data_hora']})"
            for p in historico
        ]

        # Inicia sem nenhuma prescrição pré-selecionada para não carregar automaticamente
        escolha = st.selectbox(
            "Selecione uma prescrição para gerenciar:",
            options=opcoes_presc,
            index=None,
            placeholder="Selecione uma prescrição da lista para visualizar e gerenciar...",
        )

        if escolha:
            id_selecionado = escolha.split(" | ")[0]
            presc_detalhe = next(
                p for p in historico if p["id_prescricao"] == id_selecionado
            )

            c_info1, c_info2 = st.columns([3, 1])
            with c_info1:
                st.markdown(
                    f"**Identificador:** `{presc_detalhe['id_prescricao']}` |"
                    f" **Paciente:** `{presc_detalhe['nome_paciente']}`"
                )
                st.markdown(f"**Data de Registro:** {presc_detalhe['data_hora']}")
                st.markdown(
                    "**Custo Total (PLIM):**"
                    f" `{formatar_moeda(presc_detalhe['custo_total'])}` | **Qualidade:**"
                    f" `{presc_detalhe['qualidade_total']:.0f} pts` | **Status:**"
                    f" `{presc_detalhe['status_otimizacao']}`"
                )
                if "total_comb_fb" in presc_detalhe and presc_detalhe["total_comb_fb"]:
                    st.caption(f"Espaço Amostral: `{formatar_inteiro(presc_detalhe['total_comb_fb'])}` combinações | Tempo PLIM: `{presc_detalhe.get('tempo_plim', 0.0):.4f}s` | Tempo FB: `{presc_detalhe.get('tempo_fb', 0.0):.4f}s`")

            with c_info2:
                if st.button(
                    "🗑️ Excluir Prescrição",
                    key=f"btn_del_{id_selecionado}",
                    type="secondary",
                ):
                    excluir_prescricao_salva(id_selecionado)
                    st.warning(f"Prescrição {id_selecionado} excluída.")
                    st.rerun()

            st.markdown("### 📋 Comparativo de Composição Aprovada (Lado a Lado)")
            col_comp_plim, col_comp_fb = st.columns(2)

            df_plim_salvo = pd.DataFrame(presc_detalhe.get("detalhes_plim", []))
            df_fb_salvo = pd.DataFrame(presc_detalhe.get("detalhes_fb", []))

            with col_comp_plim:
                st.markdown("**Composição Selecionada pelo Solver PLIM (CBC)**")
                if not df_plim_salvo.empty:
                    st.dataframe(
                        df_plim_salvo.style.format({
                            "Valor Unitário (R$)": formatar_moeda,
                            "Pontos de Adequação Técnica": "{:.0f}",
                        }),
                        use_container_width=True,
                    )
                else:
                    st.info("Nenhum detalhe salvo para o Solver PLIM.")

            with col_comp_fb:
                st.markdown("**Composição Selecionada pela Força Bruta**")
                if not df_fb_salvo.empty:
                    st.dataframe(
                        df_fb_salvo.style.format({
                            "Valor Unitário (R$)": formatar_moeda,
                            "Pontos de Adequação Técnica": "{:.0f}",
                        }),
                        use_container_width=True,
                    )
                else:
                    st.warning("Busca Exaustiva não salva ou não executada para esta prescrição.")

            # =================================================================
            # BLOCO DE EDIÇÃO COMPLETO
            # (Mantém o painel de edição aberto e persistente durante o rerun)
            # =================================================================
            chave_exp_ed = f"exp_ed_{id_selecionado}"
            if chave_exp_ed not in st.session_state:
                st.session_state[chave_exp_ed] = True

            with st.expander(
                "✏️ Alterar Componentes, Orçamento, Fator λ ou Qualidade por Item",
                expanded=st.session_state[chave_exp_ed],
            ):
                st.markdown(
                    f"Edite os parâmetros da prescrição **{id_selecionado}** e recalcule a otimização:"
                )

                col_ed1, col_ed2 = st.columns(2)
                with col_ed1:
                    novo_nome = st.text_input(
                        "Identificador / Nome do Paciente:",
                        value=presc_detalhe.get("nome_paciente", ""),
                        key=f"ed_nome_{id_selecionado}",
                    )
                    novo_lambda = st.slider(
                        "Fator de Ponderação (λ) desta Prescrição:",
                        0.0,
                        1.0,
                        float(presc_detalhe.get("lambda", 0.2)),
                        0.1,
                        key=f"ed_lam_{id_selecionado}",
                        help="Ajuste o trade-off entre custo e adequação técnica.",
                    )

                with col_ed2:
                    novo_orcamento = st.number_input(
                        "Teto Orçamentário Disponível (R$):",
                        min_value=500.0,
                        value=float(presc_detalhe.get("limite_orcamento", 10000.0)),
                        step=500.0,
                        key=f"ed_orc_{id_selecionado}",
                    )

                # Resgate dos termos originais para reabrir no formulário
                termos_salvos = presc_detalhe.get("termos_originais", [])

                if "RELAX" in termos_salvos:
                    modelo_salvo_def = 0
                elif "PRISMA" in termos_salvos:
                    modelo_salvo_def = 1
                else:
                    modelo_salvo_def = None

                novo_modelo_cadeira = st.selectbox(
                    "Estrutura / Modelo da Cadeira (Chassi):",
                    ["RELAX", "PRISMA"],
                    index=modelo_salvo_def,
                    placeholder="Selecione um chassi (ou deixe em branco)...",
                    key=f"ed_mod_cad_{id_selecionado}",
                )

                # Filtra os demais componentes para o campo de texto
                componentes_texto_salvos = [
                    t for t in termos_salvos if t not in ["RELAX", "PRISMA"]
                ]
                texto_inclusos_salvo = "\n".join(componentes_texto_salvos)

                novo_itens_txt = st.text_area(
                    "Componentes e Itens Prescritos (um por linha):",
                    value=texto_inclusos_salvo,
                    height=250,
                    key=f"ed_txt_inclusos_{id_selecionado}",
                    help="Edite, adicione ou exclua termos da prescrição.",
                )

                # Consolidação dos novos termos
                novos_termos_brutos = []
                if novo_modelo_cadeira is not None and novo_modelo_cadeira.strip():
                    novos_termos_brutos.append(novo_modelo_cadeira.strip())

                for linha in novo_itens_txt.split("\n"):
                    t = linha.strip()
                    if t:
                        novos_termos_brutos.append(t)

                # Reexecução do mapeamento dinâmico
                novos_itens_ids = []
                novos_itens_nao_encontrados = []
                tabela_ed_mapa = []

                for termo_e in novos_termos_brutos:
                    if termo_e in catmat_dict:
                        id_cat_e = termo_e
                        novos_itens_ids.append(id_cat_e)
                        tabela_ed_mapa.append({
                            "Termo Prescrito": termo_e,
                            "ID Catálogo Encontrado": id_cat_e,
                            "Descrição Oficial": descricoes_oficiais.get(id_cat_e, ""),
                        })
                    else:
                        id_cat_e = mapear_termo_dinamico(termo_e, descricoes_oficiais)
                        if id_cat_e:
                            novos_itens_ids.append(id_cat_e)
                            tabela_ed_mapa.append({
                                "Termo Prescrito": termo_e,
                                "ID Catálogo Encontrado": id_cat_e,
                                "Descrição Oficial": descricoes_oficiais.get(id_cat_e, ""),
                            })
                        else:
                            novos_itens_nao_encontrados.append(termo_e)
                            tabela_ed_mapa.append({
                                "Termo Prescrito": termo_e,
                                "ID Catálogo Encontrado": "NÃO ENCONTRADO",
                                "Descrição Oficial": "Sobreposição < 90%",
                            })

                novos_itens_validos_unicos = list(dict.fromkeys(novos_itens_ids))

                st.caption("📋 **Mapeamento Atualizado dos Componentes:**")
                if novos_termos_brutos:
                    st.dataframe(pd.DataFrame(tabela_ed_mapa), use_container_width=True)
                    if novos_itens_nao_encontrados:
                        st.error(
                            f"❌ Itens não mapeados no catálogo: {', '.join(novos_itens_nao_encontrados)}."
                        )

                # Avaliação técnica das notas para os novos itens (individual por item, sem repetição, mantendo aberto)
                st.markdown("#### 🎖️ Ordem de Preferência Técnica dos Fornecedores por Item:")
                mapa_qualidade_salvo = presc_detalhe.get("mapa_qualidade_item", {})
                mapa_edicao_qualidade = {}
                erro_edicao_notas = False
                componentes_ed_com_erro = []

                if novos_itens_validos_unicos and not novos_itens_nao_encontrados:
                    for k_ed in novos_itens_validos_unicos:
                        forns_ed = list(catmat_dict.get(k_ed, {}).keys())

                        with st.expander(
                            f"📦 {k_ed} - {descricoes_oficiais.get(k_ed, '')[:70]}...",
                            expanded=True,
                        ):
                            st.caption(f"**Descrição Técnica:** {descricoes_oficiais.get(k_ed, '')}")
                            cols_ed = st.columns(len(forns_ed))
                            notas_ed_k = {}

                            for idx_fe, fe in enumerate(forns_ed):
                                val_salvo = mapa_qualidade_salvo.get(k_ed, {}).get(
                                    fe, PONTOS_QUALIDADE_PADRAO.get(fe, max(1, 3 - idx_fe))
                                )
                                if val_salvo not in [3, 2, 1]:
                                    val_salvo = max(1, 3 - idx_fe)

                                with cols_ed[idx_fe]:
                                    st.markdown(f"**{fe}**")
                                    st.markdown(f"Preço: `{formatar_moeda(catmat_dict[k_ed][fe])}`")
                                    n_ed = st.selectbox(
                                        f"Avaliação ({fe}):",
                                        options=[3, 2, 1],
                                        index=[3, 2, 1].index(val_salvo),
                                        format_func=lambda x: ROTULOS_PREFERENCIA.get(x, str(x)),
                                        key=f"ed_q_{id_selecionado}_{k_ed}_{fe}",
                                    )
                                    notas_ed_k[fe] = int(n_ed)

                            valores_ed_k = list(notas_ed_k.values())
                            if len(valores_ed_k) != len(set(valores_ed_k)):
                                st.error(
                                    f"⚠️ Preferências repetidas no item **{k_ed}**. Ordene 1ª (3), 2ª (2) e 3ª (1) opção sem repetir posições."
                                )
                                erro_edicao_notas = True
                                componentes_ed_com_erro.append(k_ed)

                            mapa_edicao_qualidade[k_ed] = notas_ed_k

                # Botão para salvar alterações e recalcular
                if st.button(
                    "💾 Atualizar Prescrição e Recalcular",
                    key=f"btn_save_edit_{id_selecionado}",
                    type="primary",
                ):
                    if not novo_nome.strip():
                        st.error("O identificador do paciente não pode ficar em branco.")
                    elif existe_paciente_na_base(novo_nome, id_ignorar=id_selecionado):
                        st.error(
                            f"O identificador '{novo_nome}' já pertence a outra prescrição cadastrada."
                        )
                    elif not novos_termos_brutos:
                        st.error("A prescrição deve conter ao menos um componente.")
                    elif novos_itens_nao_encontrados:
                        st.error("❌ Corrija os termos não mapeados antes de recalcular.")
                    elif erro_edicao_notas:
                        st.error(
                            f"❌ Corrija as preferências repetidas nos seguintes componentes: {', '.join(componentes_ed_com_erro)}."
                        )
                    else:
                        with st.spinner("Recalculando modelo PLIM com os novos parâmetros..."):
                            st_plim, c_plim, q_plim, f_plim, df_d_plim, t_plim = resolver_plim(
                                novos_itens_validos_unicos,
                                novo_lambda,
                                novo_orcamento,
                                mapa_edicao_qualidade,
                            )
                            st_fb, c_fb, q_fb, f_fb, df_d_fb, tot_comb, t_fb, _ = resolver_forca_bruta(
                                novos_itens_validos_unicos,
                                novo_lambda,
                                novo_orcamento,
                                mapa_edicao_qualidade,
                            )

                            atualizar_prescricao_existente(
                                id_prescricao=id_selecionado,
                                novo_nome_paciente=novo_nome.strip(),
                                novos_termos_prescritos=novos_termos_brutos,
                                novos_itens_ids=novos_itens_validos_unicos,
                                lambda_val=novo_lambda,
                                orcamento_val=novo_orcamento,
                                status_plim=st_plim,
                                custo_plim=c_plim,
                                qual_plim=q_plim,
                                fo_plim=f_plim,
                                df_det_plim=df_d_plim,
                                status_fb=st_fb,
                                custo_fb=c_fb,
                                qual_fb=q_fb,
                                fo_fb=f_fb,
                                df_det_fb=df_d_fb,
                                tempo_plim=t_plim,
                                tempo_fb=t_fb,
                                total_comb_fb=tot_comb,
                                mapa_qualidade_item=mapa_edicao_qualidade,
                            )

                        # Grava a notificação e preserva a permanência na guia de histórico
                        st.session_state["msg_sucesso_edicao"] = (
                            f"✅ Prescrição **{id_selecionado}** ({novo_nome}) atualizada e recalculada com sucesso! "
                            f"Novo Valor: **{formatar_moeda(c_plim)}** | "
                            f"Adequação Técnica: **{q_plim:.0f} pts** | "
                            f"Situação: **{st_plim}**"
                        )
                        st.session_state["aba_ativa"] = "📂 Histórico de Prescrições Salvas"
                        st.rerun()