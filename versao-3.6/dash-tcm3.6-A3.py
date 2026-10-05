# --- Para executar este código, abra o terminal no PyCharm e digite:
# --- streamlit run dash-tcm3.6-A3.py
# --- Para encerrar a execução: ctrl + c

import os
import json
import time
import unicodedata
import re
import itertools
from datetime import datetime
import pandas as pd
import pulp
import streamlit as st

# Configuração da página do Streamlit
st.set_page_config(
    layout="wide",
    page_title="TCM 3.6-A3 - Prescrição Customizada & Otimização de Cadeiras de Rodas"
)

# Resolução dinâmica do diretório para execução robusta no Streamlit Cloud
DIRETORIO_SCRIPT = os.path.dirname(os.path.abspath(__file__))
ARQUIVO_PRESC_SALVAS = os.path.join(DIRETORIO_SCRIPT, "dataset-prescricoes-manuais.json")

# Rótulos amigáveis de avaliação técnica para o usuário clínico/gestor
ROTULOS_PREFERENCIA = {
    3: "3 - Alta Preferência (Mais indicado / Melhor acabamento)",
    2: "2 - Preferência Média (Atende aos requisitos)",
    1: "1 - Opção Básica (Menor preferência clínica)"
}


# ==========================================
# FUNÇÕES DE FORMATAÇÃO E NORMALIZAÇÃO
# ==========================================
def formatar_moeda(valor):
    if pd.isna(valor):
        return "R$ 0,00"
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def normalizar_texto(texto):
    if not texto:
        return ""
    texto = str(texto).lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    ).strip()


def formatar_inteiro(valor):
    if pd.isna(valor):
        return "0"
    return f"{int(valor):,}".replace(",", ".")


# ==========================================
# CARGA DO CATÁLOGO DE COMPONENTES
# ==========================================
@st.cache_data
def carregar_catalogo():
    path_ds7 = os.path.join(DIRETORIO_SCRIPT, "dataset_7_componentes.json")
    if not os.path.exists(path_ds7):
        path_ds7 = "dataset_7_componentes.json"

    if not os.path.exists(path_ds7):
        st.error(f"Arquivo 'dataset_7_componentes.json' não encontrado nem em '{DIRETORIO_SCRIPT}' nem na raiz.")
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

    return catmat_dict, descricoes_oficiais, categorias_dict, sorted(list(todos_fornecedores))


catmat_dict, descricoes_oficiais, categorias_dict, lista_fornecedores_catalogo = carregar_catalogo()


def formatar_opcao_catalogo(cod_item):
    cat = categorias_dict.get(cod_item, "Outros")
    desc = descricoes_oficiais.get(cod_item, "")
    desc_curta = (desc[:65] + "...") if len(desc) > 65 else desc
    return f"{cod_item} | [{cat}] {desc_curta}"


# ==========================================
# MAPEAMENTO DO GUIA CLÍNICO PARA O CATÁLOGO
# ==========================================
MAPEAMENTO_CLINICO = {
    # 1. Chassi
    "Chassi RELAX (Recliner Independente + Tilt)": "CHASSI-RELAX" if "CHASSI-RELAX" in catmat_dict else "CATMAT-400780",
    "Chassi PRISMA (Tilt do Conjunto Assento/Encosto)": "CHASSI-PRISMA" if "CHASSI-PRISMA" in catmat_dict else "CATMAT-623881",
    # 2. Almofada_Assento
    "Assento anatômico com onda": "ALM-ONDA-INF" if "ALM-ONDA-INF" in catmat_dict else "CATMAT-483711",
    "Assento plano": "ALM-PLANA-INF" if "ALM-PLANA-INF" in catmat_dict else "CATMAT-446695",
    "Assento com faixas": "CATMAT-446695",
    # 3. Suporte_Cabeca
    "Apoio de cabeça curvado": "SUP-CAB-CURV" if "SUP-CAB-CURV" in catmat_dict else "CATMAT-600560",
    "Apoio de cabeça occipital": "CATMAT-600560",
    # 4. Suporte_Postural
    "Encosto plano": "CATMAT-455920" if "CATMAT-455920" in catmat_dict else "CATMAT-455891",
    "Apoio de tronco (Estabilizadores laterais)": "CATMAT-455920" if "CATMAT-455920" in catmat_dict else "CATMAT-455888",
    "Cinto peitoral": "ACC-CINTO-PEITORAL" if "ACC-CINTO-PEITORAL" in catmat_dict else "CATMAT-477255",
    "Cinto pélvico": "CATMAT-474765" if "CATMAT-474765" in catmat_dict else "CATMAT-477257",
    "Apoio de quadril": "ACC-QUADRIL" if "ACC-QUADRIL" in catmat_dict else "CATMAT-454732",
    "Abdutor removível": "ACC-ABDUTOR-REM" if "ACC-ABDUTOR-REM" in catmat_dict else "CATMAT-455901",
    "Adutor removível": "ACC-ADUTOR-REM" if "ACC-ADUTOR-REM" in catmat_dict else "CATMAT-455902",
    # 5. Apoio_Ajustavel
    "Apoio de braços": "ACC-BRACO-GEN" if "ACC-BRACO-GEN" in catmat_dict else "CATMAT-400802",
    "Apoio de pés plástico": "CATMAT-400779" if "CATMAT-400779" in catmat_dict else "CATMAT-400778",
    "Apoio de pés caixa em madeira": "ACC-PES-CX-MAD" if "ACC-PES-CX-MAD" in catmat_dict else "CATMAT-400796",
    "Apoio de panturrilha": "CATMAT-445967",
    "Mesa de atividades": "CATMAT-409985",
    "Suporte de dieta": "ACC-SUP-DIETA" if "ACC-SUP-DIETA" in catmat_dict else "CATMAT-438188",
    # 6. Imobilizador
    "Bloqueador de joelhos": "CATMAT-452106" if "CATMAT-452106" in catmat_dict else "CATMAT-452113",
    "Posicionador de punho (Órtese)": "CATMAT-452082",
    "Faixa restringidora postural": "CATMAT-452097",
    # 7. Fixador
    "Faixa p/ pés e tornozelos": "CATMAT-482135" if "CATMAT-482135" in catmat_dict else "CATMAT-445967",
    "Faixa p/ pés": "CATMAT-445962",
    "Faixa p/ tornozelos": "CATMAT-445963",
    "Bandagem de fixação": "CATMAT-478132",
}


# ==========================================
# PERSISTÊNCIA DE PRESCRIÇÕES MANUAIS
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
    padrao = re.compile(r"^paciente#m(\d+)$", re.IGNORECASE)

    for p in prescricoes:
        nome = p.get("nome_paciente", "").strip()
        match = padrao.match(nome)
        if match:
            numeros.append(int(match.group(1)))

    if not numeros:
        proximo_num = 1
    else:
        proximo_num = max(numeros) + 1

    return f"Paciente#m{proximo_num:04d}"


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
    id_prescricao, nome_paciente, itens_ids, lambda_val, orcamento_val,
    status_plim, custo_plim, qual_plim, fo_plim, df_det_plim,
    status_fb, custo_fb, qual_fb, fo_fb, df_det_fb,
    modo_entrada, mapa_qualidade_item
):
    prescricoes = carregar_prescricoes_salvas()
    registro = {
        "id_prescricao": id_prescricao,
        "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nome_paciente": nome_paciente,
        "modo_entrada": modo_entrada,
        "itens_prescritos": itens_ids,
        "total_itens": len(itens_ids),
        "lambda": lambda_val,
        "limite_orcamento": orcamento_val,
        "status_otimizacao": status_plim,
        "custo_total": custo_plim,
        "qualidade_total": qual_plim,
        "valor_fo": fo_plim,
        "status_fb": status_fb,
        "custo_fb": custo_fb,
        "qualidade_fb": qual_fb,
        "valor_fo_fb": fo_fb,
        "mapa_qualidade_item": mapa_qualidade_item,
        "detalhes_plim": df_det_plim.to_dict(orient="records"),
        "detalhes_fb": df_det_fb.to_dict(orient="records"),
    }
    prescricoes = [p for p in prescricoes if p["id_prescricao"] != id_prescricao]
    prescricoes.insert(0, registro)
    with open(ARQUIVO_PRESC_SALVAS, "w", encoding="utf-8") as f:
        json.dump(prescricoes, f, ensure_ascii=False, indent=2)


def atualizar_prescricao_existente(
    id_prescricao, novo_nome_paciente, novos_itens_ids, lambda_val, orcamento_val,
    status_plim, custo_plim, qual_plim, fo_plim, df_det_plim,
    status_fb, custo_fb, qual_fb, fo_fb, df_det_fb,
    mapa_qualidade_item
):
    prescricoes = carregar_prescricoes_salvas()
    for p in prescricoes:
        if p["id_prescricao"] == id_prescricao:
            p["data_hora_atualizacao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            p["nome_paciente"] = novo_nome_paciente
            p["itens_prescritos"] = novos_itens_ids
            p["total_itens"] = len(novos_itens_ids)
            p["lambda"] = lambda_val
            p["limite_orcamento"] = orcamento_val
            p["status_otimizacao"] = status_plim
            p["custo_total"] = custo_plim
            p["qualidade_total"] = qual_plim
            p["valor_fo"] = fo_plim
            p["status_fb"] = status_fb
            p["custo_fb"] = custo_fb
            p["qualidade_fb"] = qual_fb
            p["valor_fo_fb"] = fo_fb
            p["mapa_qualidade_item"] = mapa_qualidade_item
            p["detalhes_plim"] = df_det_plim.to_dict(orient="records")
            p["detalhes_fb"] = df_det_fb.to_dict(orient="records")
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
def resolver_plim(itens_prescritos, lambda_param, limite_orcamento, mapa_qualidade):
    itens_validos = [k for k in itens_prescritos if k in catmat_dict]
    if not itens_validos:
        return "Inviável - Itens ausentes", 0.0, 0.0, None, pd.DataFrame()

    n_itens = len(itens_validos)
    custo_max_poss = float(sum(max(catmat_dict[k].values()) for k in itens_validos))

    qual_max_poss = float(sum(
        max(mapa_qualidade.get(k, {}).values(), default=3.0)
        for k in itens_validos
    ))
    if qual_max_poss <= 0:
        qual_max_poss = float(n_itens * 3.0)

    m = pulp.LpProblem("PLIM_Customizado", pulp.LpMinimize)

    x = {}
    for idx, k in enumerate(itens_validos):
        for f in catmat_dict[k].keys():
            var_name = f"x_{idx}_{f}".replace("-", "_").replace(" ", "_")
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

    f_custo = (float(lambda_param) / custo_max_poss) if custo_max_poss > 0 else float(lambda_param)
    f_qual = (float(1.0 - lambda_param) / qual_max_poss) if qual_max_poss > 0 else float(1.0 - lambda_param)

    m += (f_custo * custo_total) - (f_qual * qualidade_total)

    for idx, k in enumerate(itens_validos):
        m += pulp.lpSum(x[idx, k, f] for f in catmat_dict[k].keys()) == 1

    m += custo_total <= float(limite_orcamento)

    m.solve(pulp.PULP_CBC_CMD(msg=0))

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
                        "Pontos de Adequação Técnica": nota_f
                    })
    else:
        status = f"Orçamento Insuficiente (Limite: {formatar_moeda(limite_orcamento)})"
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
                "Pontos de Adequação Técnica": mapa_qualidade.get(k, {}).get(f_min, 1)
            })

    return status, custo, qualidade, fo, pd.DataFrame(detalhes)


def resolver_forca_bruta(itens_prescritos, lambda_param, limite_orcamento, mapa_qualidade):
    itens_validos = [k for k in itens_prescritos if k in catmat_dict]
    if not itens_validos:
        return "Inviável - Itens ausentes", 0.0, 0.0, None, pd.DataFrame(), 0, 0.0, "0 = 0"

    t0 = time.time()
    n_itens = len(itens_validos)
    custo_max_poss = float(sum(max(catmat_dict[k].values()) for k in itens_validos))

    qual_max_poss = float(sum(
        max(mapa_qualidade.get(k, {}).values(), default=3.0)
        for k in itens_validos
    ))
    if qual_max_poss <= 0:
        qual_max_poss = float(n_itens * 3.0)

    opcoes_fornecedores = [list(catmat_dict[k].keys()) for k in itens_validos]

    total_combinacoes = 1
    for op in opcoes_fornecedores:
        total_combinacoes *= len(op)

    melhor_fo = float("inf")
    melhor_comb = None
    melhor_custo = 0.0
    melhor_qual = 0.0

    for comb in itertools.product(*opcoes_fornecedores):
        custo_comb = sum(catmat_dict[k][f] for k, f in zip(itens_validos, comb))
        if custo_comb <= limite_orcamento:
            qual_comb = sum(mapa_qualidade.get(k, {}).get(f, 1) for k, f in zip(itens_validos, comb))
            c_norm = (custo_comb / custo_max_poss) if custo_max_poss > 0 else custo_comb
            q_norm = (qual_comb / qual_max_poss) if qual_max_poss > 0 else qual_comb
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
                "Pontos de Adequação Técnica": mapa_qualidade.get(k, {}).get(f, 1)
            })
    else:
        status = f"Orçamento Insuficiente (Limite: {formatar_moeda(limite_orcamento)})"
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
                "Pontos de Adequação Técnica": mapa_qualidade.get(k, {}).get(f_min, 1)
            })

    tempo_exec = time.time() - t0
    racional_calculo = " × ".join([str(len(op)) for op in opcoes_fornecedores]) + f" = {formatar_inteiro(total_combinacoes)}"

    return (
        status, melhor_custo, melhor_qual, melhor_fo,
        pd.DataFrame(detalhes), total_combinacoes, tempo_exec, racional_calculo
    )


# ==========================================
# INTERFACE STREAMLIT (UI)
# ==========================================
st.title("♿ TCM 3.6-A3 - Prescrição Customizada & Otimização")
st.markdown(
    "Sistema de apoio à decisão para customização de cadeiras de rodas personalizadas. "
    "Permite balancear **adequação técnica clínica** e **economicidade orçamentária**, com execução via **Solver PLIM** e **Busca Exaustiva**."
)

# ----------------------------------------------------
# BARRA LATERAL (DIRETRIZES DE DECISÃO)
# ----------------------------------------------------
st.sidebar.header("⚖️ Diretrizes de Decisão")

st.sidebar.markdown(
    "Defina como o algoritmo deve ponderar as prescições:"
)

LAMBDA = st.sidebar.slider(
    "Foco de Otimização (Econômico vs. Técnico):",
    0.0, 1.0, 0.2, 0.1,
    help="Valores mais baixos priorizam a qualidade técnica e os acabamentos; valores mais altos buscam o menor preço dentro do catálogo."
)

perc_economia = int(round(LAMBDA * 100))
perc_qualidade = int(round((1 - LAMBDA) * 100))

col_p1, col_p2 = st.sidebar.columns(2)
col_p1.metric("Prioridade Técnica", f"{perc_qualidade}%")
col_p2.metric("Economia Orçamentária", f"{perc_economia}%")

LIMITE_ORCAMENTO = st.sidebar.number_input(
    "Teto Orçamentário Disponível (R$):",
    min_value=500.0,
    value=10000.0,
    step=500.0,
    help="Limite máximo de investimento autorizado para a cadeira deste paciente."
)

# ----------------------------------------------------
# NAVEGAÇÃO POR ABAS
# ----------------------------------------------------
tab_nova, tab_historico = st.tabs(["📝 Nova Prescrição & Otimização", "📂 Histórico de Prescrições Salvas"])

padrao_inicial_notas = {"Fornecedor-A": 3, "Fornecedor-B": 2, "Fornecedor-C": 1}

# ----------------------------------------------------
# ABA 1: NOVA PRESCRIÇÃO & OTIMIZAÇÃO
# ----------------------------------------------------
with tab_nova:
    col_id1, col_id2 = st.columns([1, 1])
    id_sugestao = f"PRESC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    paciente_sugestao = obter_proximo_identificador_paciente()

    with col_id1:
        id_prescricao_input = st.text_input(
            "Código de Identificação da Prescrição (Automático):",
            value=id_sugestao,
            disabled=True,
            help="Identificador único gerado automaticamente pelo sistema com carimbo temporal."
        )
    with col_id2:
        nome_paciente_input = st.text_input(
            "Identificador / Nome do Paciente:",
            value=paciente_sugestao,
            help="Identificador anônimo sequencial sugerido automaticamente para garantir a privacidade."
        )

    modo_entrada = st.radio(
        "Selecione a forma de indicação dos itens:",
        [
            "Guia Clínico Estruturado (7 Categorias da Dissertação)",
            "Seleção Direta por Código de Catálogo (CATMAT)"
        ],
        horizontal=True
    )

    itens_selecionados_ids = []

    if modo_entrada == "Guia Clínico Estruturado (7 Categorias da Dissertação)":
        st.info("💡 Indique os componentes clínicos necessários organizados pelas 7 categorias funcionais.")

        c_col1, c_col2 = st.columns(2)

        with c_col1:
            # 1. Chassi (Seleção obrigatória e unívoca de Chassi)
            st.subheader("1. Chassi Estrutural (Obrigatório escolher exatamente 1)")
            opcao_chassi = st.radio(
                "Estrutura base da cadeira:",
                options=[
                    "Chassi RELAX (Recliner Independente + Tilt)",
                    "Chassi PRISMA (Tilt do Conjunto Assento/Encosto)"
                ],
                index=None,  # <-- Inicia sem nenhum chassi marcado
                help="Toda cadeira de rodas precisa ter uma única estrutura principal definida."
            )
            # Adiciona aos itens prescritos se o usuário tiver feito a escolha
            if opcao_chassi is not None:
                itens_selecionados_ids.append(MAPEAMENTO_CLINICO[opcao_chassi])

            # 2. Almofada_Assento
            st.subheader("2. Almofada do Assento")
            check_assento_onda = st.checkbox("Assento anatômico com onda", value=False)
            check_assento_plano = st.checkbox("Assento plano", value=False)
            check_assento_faixas = st.checkbox("Assento com faixas", value=False)
            if check_assento_onda: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Assento anatômico com onda"])
            if check_assento_plano: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Assento plano"])
            if check_assento_faixas: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Assento com faixas"])

            # 3. Suporte_Cabeca
            st.subheader("3. Suporte de Cabeça")
            check_cab_curv = st.checkbox("Apoio de cabeça curvado", value=False)
            check_cab_occip = st.checkbox("Apoio de cabeça occipital", value=False)
            if check_cab_curv: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Apoio de cabeça curvado"])
            if check_cab_occip: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Apoio de cabeça occipital"])

            # 4. Suporte_Postural
            st.subheader("4. Suporte Postural (Tronco e Pelve)")
            check_encosto = st.checkbox("Encosto plano", value=False)
            check_tronco = st.checkbox("Apoio de tronco (Estabilizadores laterais)", value=False)
            check_peitoral = st.checkbox("Cinto peitoral", value=False)
            check_pelvico = st.checkbox("Cinto pélvico", value=False)
            check_quadril = st.checkbox("Apoio de quadril", value=False)
            check_abdutor = st.checkbox("Abdutor removível", value=False)
            check_adutor = st.checkbox("Adutor removível", value=False)

            if check_encosto: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Encosto plano"])
            if check_tronco: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Apoio de tronco (Estabilizadores laterais)"])
            if check_peitoral: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Cinto peitoral"])
            if check_pelvico: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Cinto pélvico"])
            if check_quadril: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Apoio de quadril"])
            if check_abdutor: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Abdutor removível"])
            if check_adutor: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Adutor removível"])

        with c_col2:
            # 5. Apoio_Ajustavel
            st.subheader("5. Apoios Ajustáveis e Acessórios")
            check_braco = st.checkbox("Apoio de braços", value=False)
            check_pes = st.checkbox("Apoio de pés plástico", value=False)
            check_pes_mad = st.checkbox("Apoio de pés caixa em madeira", value=False)
            check_pant = st.checkbox("Apoio de panturrilha", value=False)
            check_mesa = st.checkbox("Mesa de atividades", value=False)
            check_dieta = st.checkbox("Suporte de dieta", value=False)

            if check_braco: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Apoio de braços"])
            if check_pes: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Apoio de pés plástico"])
            if check_pes_mad: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Apoio de pés caixa em madeira"])
            if check_pant: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Apoio de panturrilha"])
            if check_mesa: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Mesa de atividades"])
            if check_dieta: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Suporte de dieta"])

            # 6. Imobilizador
            st.subheader("6. Imobilizadores e Contenção Rígida")
            check_bloq_joelho = st.checkbox("Bloqueador de joelhos", value=False)
            check_pos_punho = st.checkbox("Posicionador de punho (Órtese)", value=False)
            check_faixa_rest = st.checkbox("Faixa restringidora postural", value=False)

            if check_bloq_joelho: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Bloqueador de joelhos"])
            if check_pos_punho: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Posicionador de punho (Órtese)"])
            if check_faixa_rest: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Faixa restringidora postural"])

            # 7. Fixador
            st.subheader("7. Fixadores e Bandagens")
            check_fx_pes_torn = st.checkbox("Faixa p/ pés e tornozelos", value=False)
            check_fx_pes = st.checkbox("Faixa p/ pés", value=False)
            check_fx_torn = st.checkbox("Faixa p/ tornozelos", value=False)
            check_bandagem = st.checkbox("Bandagem de fixação", value=False)

            if check_fx_pes_torn: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Faixa p/ pés e tornozelos"])
            if check_fx_pes: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Faixa p/ pés"])
            if check_fx_torn: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Faixa p/ tornozelos"])
            if check_bandagem: itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Bandagem de fixação"])

    else:
        st.info("💡 Seleção técnica direta dos itens catalogados na base de compras.")
        todos_componentes = list(catmat_dict.keys())
        itens_selecionados_ids = st.multiselect(
            "Selecione os itens do catálogo que irão compor a cadeira:",
            options=todos_componentes,
            default=[],
            format_func=formatar_opcao_catalogo,
            help="Pesquise por código CATMAT, categoria técnica ou termos da descrição oficial."
        )

        chassis_no_catalogo = [cod for cod in itens_selecionados_ids if categorias_dict.get(cod) == "Chassi"]
        if len(chassis_no_catalogo) == 0:
            st.warning("⚠️ Atenção: É obrigatório incluir exatamente 1 chassi estrutural na composição.")
        elif len(chassis_no_catalogo) > 1:
            st.error(f"❌ Atenção: Foram selecionados {len(chassis_no_catalogo)} chassis ({', '.join(chassis_no_catalogo)}). Deixe apenas 1 modelo.")

    itens_selecionados_ids = list(dict.fromkeys(itens_selecionados_ids))

    st.divider()

    # ====================================================
    # BLOCO DE AVALIAÇÃO DE PREFERÊNCIA TÉCNICA
    # ====================================================
    st.subheader("🎖️ Ordem de Preferência Técnica dos Fornecedores")
    st.markdown(
        "Para cada componente selecionado, ordene as opções de fornecedores indicando qual deles oferece o melhor "
        "adequação clínica para este caso específico:\n\n"
        "- **3 - Alta Preferência**: Primeira escolha (opção tecnicamente mais recomendada)\n"
        "- **2 - Preferência Média**: Segunda escolha (atende perfeitamente aos requisitos)\n"
        "- **1 - Opção Básica**: Terceira escolha (opção de menor preferência clínica)\n\n"
    )

    mapa_qualidade_coletado = {}
    erro_notas_duplicadas = False
    componentes_com_erro = []

    if itens_selecionados_ids:
        for cod_item in itens_selecionados_ids:
            desc_item = descricoes_oficiais.get(cod_item, "Sem descrição")
            cat_item = categorias_dict.get(cod_item, "Outros")
            fornecedores_item = list(catmat_dict.get(cod_item, {}).keys())

            with st.expander(f"📦 [{cat_item}] {cod_item} - {desc_item[:70]}...", expanded=True):
                st.caption(f"**Descrição Técnica Completa:** {desc_item}")
                cols_forn = st.columns(len(fornecedores_item))
                notas_item = {}

                for idx_f, forn in enumerate(fornecedores_item):
                    preco_ref = catmat_dict[cod_item][forn]
                    val_def = padrao_inicial_notas.get(forn, max(1, 3 - idx_f))

                    with cols_forn[idx_f]:
                        st.markdown(f"**{forn}**")
                        st.markdown(f"Preço de Referência: `{formatar_moeda(preco_ref)}`")
                        nota = st.selectbox(
                            f"Avaliação ({forn}):",
                            options=[3, 2, 1],
                            index=[3, 2, 1].index(val_def) if val_def in [3, 2, 1] else 0,
                            format_func=lambda x: ROTULOS_PREFERENCIA.get(x, str(x)),
                            key=f"qual_{cod_item}_{forn}",
                            help="Indique a prioridade técnica deste fornecedor para este paciente específico."
                        )
                        notas_item[forn] = nota

                valores_notas_item = list(notas_item.values())
                if len(valores_notas_item) != len(set(valores_notas_item)):
                    st.error(
                        f"⚠️ **Ajuste de preferência no item {cod_item}:** Foram atribuídas opções repetidas. "
                        "Por favor, ordene os fornecedores em 1ª (3), 2ª (2) e 3ª (1) opção sem repetir posições."
                    )
                    erro_notas_duplicadas = True
                    componentes_com_erro.append(cod_item)

                mapa_qualidade_coletado[cod_item] = notas_item
    else:
        st.info("Selecione os componentes acima para visualizar e ordenar os fornecedores homologados.")

    st.divider()

    st.subheader(f"📋 Resumo da Prescrição Definida ({len(itens_selecionados_ids)} itens)")
    if itens_selecionados_ids:
        tabela_itens_resumo = []
        for cod in itens_selecionados_ids:
            qtd_forn = len(catmat_dict.get(cod, {}).keys())
            det_forn = []
            for f in catmat_dict.get(cod, {}).keys():
                nota_atrib = mapa_qualidade_coletado.get(cod, {}).get(f, "-")
                rotulo_curto = {3: "1ª Opção (Alta)", 2: "2ª Opção (Média)", 1: "3ª Opção (Básica)"}.get(nota_atrib, f"Nota {nota_atrib}")
                det_forn.append(f"{f}: {rotulo_curto}")

            tabela_itens_resumo.append({
                "Código CATMAT": cod,
                "Categoria": categorias_dict.get(cod, "N/A"),
                "Descrição Oficial": descricoes_oficiais.get(cod, "N/A"),
                "Ordem de Preferência dos Fornecedores": "; ".join(det_forn),
                "Qtd. Opções": qtd_forn
            })
        st.dataframe(pd.DataFrame(tabela_itens_resumo), use_container_width=True)
    else:
        st.warning("Nenhum componente selecionado até o momento.")

    if st.button("🚀 Calcular Melhor Combinação e Salvar Prescrição", type="primary"):
        nome_paciente_final = nome_paciente_input.strip()

        if not nome_paciente_final:
            st.error("Por favor, preencha o campo com a identificação do paciente.")
            st.stop()

        if not itens_selecionados_ids:
            st.error("Selecione ao menos um componente antes de realizar o cálculo.")
            st.stop()

        chassis_sel = [cod for cod in itens_selecionados_ids if categorias_dict.get(cod) == "Chassi"]
        if len(chassis_sel) == 0:
            st.error("❌ É obrigatório escolher 1 chassi estrutural para a cadeira.")
            st.stop()
        elif len(chassis_sel) > 1:
            st.error(f"❌ Foram selecionados {len(chassis_sel)} chassis ({', '.join(chassis_sel)}). A cadeira pode ter apenas 1 modelo.")
            st.stop()

        if existe_paciente_na_base(nome_paciente_final):
            st.error(f"O identificador '{nome_paciente_final}' já existe nos registros. Use uma numeração sequencial diferente.")
            st.stop()

        if erro_notas_duplicadas:
            st.error(
                f"❌ Identificamos preferências repetidas nos seguintes componentes: {', '.join(componentes_com_erro)}. "
                "Distribua as posições (1ª, 2ª e 3ª) de forma exclusiva em cada um antes de prosseguir."
            )
            st.stop()

        with st.spinner("Processando a melhor combinação custo-benefício..."):
            status_plim, custo_plim, qual_plim, fo_plim, df_det_plim = resolver_plim(
                itens_selecionados_ids, LAMBDA, LIMITE_ORCAMENTO, mapa_qualidade_coletado
            )

            (
                status_fb, custo_fb, qual_fb, fo_fb, df_det_fb,
                total_comb_fb, tempo_fb, racional_espaco
            ) = resolver_forca_bruta(
                itens_selecionados_ids, LAMBDA, LIMITE_ORCAMENTO, mapa_qualidade_coletado
            )

            salvar_nova_prescricao(
                id_prescricao=id_prescricao_input,
                nome_paciente=nome_paciente_final,
                itens_ids=itens_selecionados_ids,
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
                modo_entrada=modo_entrada,
                mapa_qualidade_item=mapa_qualidade_coletado
            )

        st.success(f"Prescrição {id_prescricao_input} ({nome_paciente_final}) calculada e arquivada com sucesso.")

        st.header("📊 Resultado da Combinação Recomendada")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Situação do Orçamento", status_plim)
        c2.metric("Valor Total da Cadeira", formatar_moeda(custo_plim), f"Teto: {formatar_moeda(LIMITE_ORCAMENTO)}")
        c3.metric("Nível de Adequação Técnica", f"{qual_plim:.0f} pts", f"Máx: {len(itens_selecionados_ids)*3} pts")
        fo_plim_str = f"{fo_plim:.4f}" if fo_plim is not None else "N/A"
        c4.metric("Índice de Equilíbrio Custo-Benefício", fo_plim_str, help="Menores valores indicam maior convergência com suas diretrizes.")

        st.info(
            f"🔍 **Auditoria Algorítmica Concluída:** O modelo de Programação Linear Inteira Mista (PLIM) "
            f"avaliou o espaço de `{formatar_inteiro(total_comb_fb)}` combinações possíveis em `{tempo_fb:.4f}` segundos, "
            f"garantindo a solução ótima global sem risco de escolhas arbitrárias."
        )

        st.subheader("🔍 Fornecedores Selecionados para Cada Componente")
        st.dataframe(
            df_det_plim.style.format({
                "Valor Unitário (R$)": formatar_moeda,
                "Pontos de Adequação Técnica": "{:.0f}"
            }),
            use_container_width=True
        )

# ----------------------------------------------------
# ABA 2: HISTÓRICO DE PRESCRIÇÕES SALVAS
# ----------------------------------------------------
with tab_historico:
    st.header("📂 Gerenciamento de Prescrições (Consultar / Alterar / Excluir)")
    historico = carregar_prescricoes_salvas()

    if not historico:
        st.info("Nenhuma prescrição cadastrada até o momento.")
    else:
        df_hist = pd.DataFrame(historico)
        colunas_exibir = [
            "id_prescricao", "data_hora", "nome_paciente", "total_itens",
            "status_otimizacao", "custo_total", "qualidade_total", "valor_fo",
            "lambda", "limite_orcamento"
        ]

        for c in colunas_exibir:
            if c not in df_hist.columns:
                df_hist[c] = None

        df_hist_vis = df_hist[colunas_exibir].rename(columns={
            "id_prescricao": "ID Prescrição",
            "data_hora": "Data/Hora",
            "nome_paciente": "Paciente / Identificador",
            "total_itens": "Qtd. Itens",
            "status_otimizacao": "Situação",
            "custo_total": "Valor Total",
            "qualidade_total": "Adequação Técnica",
            "valor_fo": "Índice Custo-Benefício",
            "lambda": "Fator Econômico (λ)",
            "limite_orcamento": "Teto Orçamentário"
        })

        st.dataframe(
            df_hist_vis.style.format({
                "Valor Total": formatar_moeda,
                "Teto Orçamentário": formatar_moeda,
                "Adequação Técnica": "{:.0f} pts",
                "Índice Custo-Benefício": lambda x: f"{x:.4f}" if pd.notna(x) else "N/A",
                "Fator Econômico (λ)": "{:.2f}"
            }),
            use_container_width=True
        )

        json_bytes = json.dumps(historico, ensure_ascii=False, indent=2).encode("utf-8")
        st.download_button(
            label="📥 Exportar Base Completa em JSON",
            data=json_bytes,
            file_name="dataset-prescricoes-manuais.json",
            mime="application/json"
        )

        st.divider()
        st.subheader("🛠️ Detalhes e Ajustes da Prescrição")

        opcoes_presc = [f"{p['id_prescricao']} | {p['nome_paciente']} ({p['data_hora']})" for p in historico]
        escolha = st.selectbox("Selecione uma prescrição para gerenciar:", opcoes_presc)

        if escolha:
            id_selecionado = escolha.split(" | ")[0]
            presc_detalhe = next(p for p in historico if p["id_prescricao"] == id_selecionado)

            mapa_qualidade_salvo = presc_detalhe.get("mapa_qualidade_item", {})

            c_info1, c_info2 = st.columns([3, 1])
            with c_info1:
                st.markdown(f"**Identificador:** `{presc_detalhe['id_prescricao']}` | **Paciente:** `{presc_detalhe['nome_paciente']}`")
                st.markdown(f"**Data de Registro:** {presc_detalhe['data_hora']} | **Método:** {presc_detalhe.get('modo_entrada', 'N/A')}")
                st.markdown(f"**Investimento Total:** `{formatar_moeda(presc_detalhe['custo_total'])}` | **Adequação Clínica:** `{presc_detalhe['qualidade_total']:.0f} pts` | **Situação:** `{presc_detalhe['status_otimizacao']}`")

            with c_info2:
                if st.button("🗑️ Excluir Prescrição", key=f"btn_del_{id_selecionado}", type="secondary"):
                    excluir_prescricao_salva(id_selecionado)
                    st.warning(f"Prescrição {id_selecionado} excluída com sucesso.")
                    st.rerun()

            if "detalhes_plim" in presc_detalhe:
                df_det_plim_hist = pd.DataFrame(presc_detalhe["detalhes_plim"])
            else:
                lam = float(presc_detalhe.get("lambda", 0.2))
                orc = float(presc_detalhe.get("limite_orcamento", 10000.0))
                _, _, _, _, df_det_plim_hist = resolver_plim(presc_detalhe["itens_prescritos"], lam, orc, mapa_qualidade_salvo)

            st.markdown("### 🔍 Composição Aprovada")
            if not df_det_plim_hist.empty:
                st.dataframe(
                    df_det_plim_hist.style.format({
                        "Valor Unitário (R$)": formatar_moeda,
                        "Pontos de Adequação Técnica": "{:.0f}"
                    }),
                    use_container_width=True
                )

            # =================================================================
            # BLOCO DE EDIÇÃO ESTRUTURADO PELAS 7 CATEGORIAS CLÍNICAS
            # =================================================================
            with st.expander("✏️ Alterar Itens ou Reavaliar esta Prescrição"):
                st.markdown(f"Ajuste a prescrição **{id_selecionado}** pelas **7 Categorias Funcionais**:")

                col_ed1, col_ed2 = st.columns(2)
                with col_ed1:
                    novo_nome = st.text_input(
                        "Identificador / Nome do Paciente:",
                        value=presc_detalhe["nome_paciente"],
                        key=f"ed_nome_{id_selecionado}"
                    )
                    novo_lambda = st.slider(
                        "Foco de Otimização (Econômico vs. Técnico):",
                        0.0, 1.0,
                        float(presc_detalhe.get("lambda", 0.2)), 0.1,
                        key=f"ed_lam_{id_selecionado}",
                        help="Ajuste para dar mais peso ao preço ou à qualidade dos itens."
                    )
                with col_ed2:
                    novo_orcamento = st.number_input(
                        "Teto Orçamentário (R$):",
                        min_value=500.0,
                        value=float(presc_detalhe.get("limite_orcamento", 10000.0)),
                        step=500.0,
                        key=f"ed_orc_{id_selecionado}"
                    )

                itens_guardados_set = set(presc_detalhe.get("itens_prescritos", []))

                st.markdown("---")
                st.subheader("📋 Composição Clínica da Cadeira (7 Categorias)")

                novos_itens_escolhidos = []
                c_ed_col1, c_ed_col2 = st.columns(2)

                with c_ed_col1:
                    # 1. Chassi
                    st.markdown("#### 1. Chassi Estrutural (Obrigatório escolher exatamente 1)")
                    opcoes_chassi_nomes = [
                        "Chassi RELAX (Recliner Independente + Tilt)",
                        "Chassi PRISMA (Tilt do Conjunto Assento/Encosto)"
                    ]
                    idx_chassi_def = 0
                    for idx_c, nome_c in enumerate(opcoes_chassi_nomes):
                        if MAPEAMENTO_CLINICO.get(nome_c) in itens_guardados_set:
                            idx_chassi_def = idx_c
                            break

                    chassi_ed_escolhido = st.radio(
                        "Estrutura base da cadeira:",
                        options=opcoes_chassi_nomes,
                        index=idx_chassi_def,
                        key=f"ed_chassi_{id_selecionado}",
                        help="Selecione obrigatoriamente um único modelo de chassi."
                    )
                    novos_itens_escolhidos.append(MAPEAMENTO_CLINICO[chassi_ed_escolhido])

                    # 2. Almofada_Assento
                    st.markdown("#### 2. Almofada do Assento")
                    ed_assento_onda = st.checkbox("Assento anatômico com onda", value=(MAPEAMENTO_CLINICO["Assento anatômico com onda"] in itens_guardados_set), key=f"ed_ck_onda_{id_selecionado}")
                    ed_assento_plano = st.checkbox("Assento plano", value=(MAPEAMENTO_CLINICO["Assento plano"] in itens_guardados_set), key=f"ed_ck_plano_{id_selecionado}")
                    ed_assento_faixas = st.checkbox("Assento com faixas", value=(MAPEAMENTO_CLINICO["Assento com faixas"] in itens_guardados_set), key=f"ed_ck_faixas_{id_selecionado}")
                    if ed_assento_onda: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Assento anatômico com onda"])
                    if ed_assento_plano: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Assento plano"])
                    if ed_assento_faixas: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Assento com faixas"])

                    # 3. Suporte_Cabeca
                    st.markdown("#### 3. Suporte de Cabeça")
                    ed_cab_curv = st.checkbox("Apoio de cabeça curvado", value=(MAPEAMENTO_CLINICO["Apoio de cabeça curvado"] in itens_guardados_set), key=f"ed_ck_curv_{id_selecionado}")
                    ed_cab_occip = st.checkbox("Apoio de cabeça occipital", value=(MAPEAMENTO_CLINICO["Apoio de cabeça occipital"] in itens_guardados_set), key=f"ed_ck_occip_{id_selecionado}")
                    if ed_cab_curv: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Apoio de cabeça curvado"])
                    if ed_cab_occip: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Apoio de cabeça occipital"])

                    # 4. Suporte_Postural
                    st.markdown("#### 4. Suporte Postural (Tronco e Pelve)")
                    ed_encosto = st.checkbox("Encosto plano", value=(MAPEAMENTO_CLINICO["Encosto plano"] in itens_guardados_set), key=f"ed_ck_encosto_{id_selecionado}")
                    ed_tronco = st.checkbox("Apoio de tronco (Estabilizadores laterais)", value=(MAPEAMENTO_CLINICO["Apoio de tronco (Estabilizadores laterais)"] in itens_guardados_set), key=f"ed_ck_tronco_{id_selecionado}")
                    ed_peitoral = st.checkbox("Cinto peitoral", value=(MAPEAMENTO_CLINICO["Cinto peitoral"] in itens_guardados_set), key=f"ed_ck_peitoral_{id_selecionado}")
                    ed_pelvico = st.checkbox("Cinto pélvico", value=(MAPEAMENTO_CLINICO["Cinto pélvico"] in itens_guardados_set), key=f"ed_ck_pelvico_{id_selecionado}")
                    ed_quadril = st.checkbox("Apoio de quadril", value=(MAPEAMENTO_CLINICO["Apoio de quadril"] in itens_guardados_set), key=f"ed_ck_quadril_{id_selecionado}")
                    ed_abdutor = st.checkbox("Abdutor removível", value=(MAPEAMENTO_CLINICO["Abdutor removível"] in itens_guardados_set), key=f"ed_ck_abdutor_{id_selecionado}")
                    ed_adutor = st.checkbox("Adutor removível", value=(MAPEAMENTO_CLINICO["Adutor removível"] in itens_guardados_set), key=f"ed_ck_adutor_{id_selecionado}")
                    if ed_encosto: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Encosto plano"])
                    if ed_tronco: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Apoio de tronco (Estabilizadores laterais)"])
                    if ed_peitoral: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Cinto peitoral"])
                    if ed_pelvico: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Cinto pélvico"])
                    if ed_quadril: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Apoio de quadril"])
                    if ed_abdutor: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Abdutor removível"])
                    if ed_adutor: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Adutor removível"])

                with c_ed_col2:
                    # 5. Apoio_Ajustavel
                    st.markdown("#### 5. Apoios Ajustáveis e Acessórios")
                    ed_braco = st.checkbox("Apoio de braços", value=(MAPEAMENTO_CLINICO["Apoio de braços"] in itens_guardados_set), key=f"ed_ck_braco_{id_selecionado}")
                    ed_pes = st.checkbox("Apoio de pés plástico", value=(MAPEAMENTO_CLINICO["Apoio de pés plástico"] in itens_guardados_set), key=f"ed_ck_pes_{id_selecionado}")
                    ed_pes_mad = st.checkbox("Apoio de pés caixa em madeira", value=(MAPEAMENTO_CLINICO["Apoio de pés caixa em madeira"] in itens_guardados_set), key=f"ed_ck_pesmad_{id_selecionado}")
                    ed_pant = st.checkbox("Apoio de panturrilha", value=(MAPEAMENTO_CLINICO["Apoio de panturrilha"] in itens_guardados_set), key=f"ed_ck_pant_{id_selecionado}")
                    ed_mesa = st.checkbox("Mesa de atividades", value=(MAPEAMENTO_CLINICO["Mesa de atividades"] in itens_guardados_set), key=f"ed_ck_mesa_{id_selecionado}")
                    ed_dieta = st.checkbox("Suporte de dieta", value=(MAPEAMENTO_CLINICO["Suporte de dieta"] in itens_guardados_set), key=f"ed_ck_dieta_{id_selecionado}")
                    if ed_braco: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Apoio de braços"])
                    if ed_pes: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Apoio de pés plástico"])
                    if ed_pes_mad: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Apoio de pés caixa em madeira"])
                    if ed_pant: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Apoio de panturrilha"])
                    if ed_mesa: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Mesa de atividades"])
                    if ed_dieta: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Suporte de dieta"])

                    # 6. Imobilizador
                    st.markdown("#### 6. Imobilizadores e Contenção Rígida")
                    ed_bloq_joelho = st.checkbox("Bloqueador de joelhos", value=(MAPEAMENTO_CLINICO["Bloqueador de joelhos"] in itens_guardados_set), key=f"ed_ck_joelho_{id_selecionado}")
                    ed_pos_punho = st.checkbox("Posicionador de punho (Órtese)", value=(MAPEAMENTO_CLINICO["Posicionador de punho (Órtese)"] in itens_guardados_set), key=f"ed_ck_punho_{id_selecionado}")
                    ed_faixa_rest = st.checkbox("Faixa restringidora postural", value=(MAPEAMENTO_CLINICO["Faixa restringidora postural"] in itens_guardados_set), key=f"ed_ck_restr_{id_selecionado}")
                    if ed_bloq_joelho: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Bloqueador de joelhos"])
                    if ed_pos_punho: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Posicionador de punho (Órtese)"])
                    if ed_faixa_rest: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Faixa restringidora postural"])

                    # 7. Fixador
                    st.markdown("#### 7. Fixadores e Bandagens")
                    ed_fx_pes_torn = st.checkbox("Faixa p/ pés e tornozelos", value=(MAPEAMENTO_CLINICO["Faixa p/ pés e tornozelos"] in itens_guardados_set), key=f"ed_ck_pestorn_{id_selecionado}")
                    ed_fx_pes = st.checkbox("Faixa p/ pés", value=(MAPEAMENTO_CLINICO["Faixa p/ pés"] in itens_guardados_set), key=f"ed_ck_fxpes_{id_selecionado}")
                    ed_fx_torn = st.checkbox("Faixa p/ tornozelos", value=(MAPEAMENTO_CLINICO["Faixa p/ tornozelos"] in itens_guardados_set), key=f"ed_ck_fxtorn_{id_selecionado}")
                    ed_bandagem = st.checkbox("Bandagem de fixação", value=(MAPEAMENTO_CLINICO["Bandagem de fixação"] in itens_guardados_set), key=f"ed_ck_band_{id_selecionado}")
                    if ed_fx_pes_torn: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Faixa p/ pés e tornozelos"])
                    if ed_fx_pes: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Faixa p/ pés"])
                    if ed_fx_torn: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Faixa p/ tornozelos"])
                    if ed_bandagem: novos_itens_escolhidos.append(MAPEAMENTO_CLINICO["Bandagem de fixação"])

                novos_itens_escolhidos = list(dict.fromkeys(novos_itens_escolhidos))

                st.markdown("---")
                st.markdown("#### 🎖️ Ordem de Preferência Técnica dos Fornecedores:")
                mapa_edicao_qualidade = {}
                erro_edicao_notas = False

                for k_ed in novos_itens_escolhidos:
                    forns_ed = list(catmat_dict.get(k_ed, {}).keys())
                    st.caption(f"**Item {k_ed}:** {descricoes_oficiais.get(k_ed, '')[:70]}...")
                    cols_ed = st.columns(len(forns_ed))
                    notas_ed_k = {}

                    for idx_fe, fe in enumerate(forns_ed):
                        val_salvo = mapa_qualidade_salvo.get(k_ed, {}).get(
                            fe, padrao_inicial_notas.get(fe, max(1, 3 - idx_fe))
                        )
                        with cols_ed[idx_fe]:
                            n_ed = st.selectbox(
                                f"Opção ({fe}):",
                                options=[3, 2, 1],
                                index=[3, 2, 1].index(val_salvo) if val_salvo in [3, 2, 1] else 0,
                                format_func=lambda x: ROTULOS_PREFERENCIA.get(x, str(x)),
                                key=f"ed_q_{id_selecionado}_{k_ed}_{fe}",
                            )
                            notas_ed_k[fe] = n_ed

                    if len(notas_ed_k.values()) != len(set(notas_ed_k.values())):
                        st.error(f"⚠️ Atenção em **{k_ed}**: Evite posições repetidas para o mesmo componente. Defina 1ª, 2ª e 3ª opção.")
                        erro_edicao_notas = True

                    mapa_edicao_qualidade[k_ed] = notas_ed_k

                if st.button("💾 Atualizar Prescrição e Recalcular", key=f"btn_save_edit_{id_selecionado}", type="primary"):
                    if not novo_nome.strip():
                        st.error("O identificador do paciente não pode ficar em branco.")
                    elif existe_paciente_na_base(novo_nome, id_ignorar=id_selecionado):
                        st.error(f"O identificador '{novo_nome}' já pertence a outra prescrição cadastrada.")
                    elif not novos_itens_escolhidos:
                        st.error("A prescrição deve conter ao menos um componente.")
                    else:
                        chassis_edicao = [cod for cod in novos_itens_escolhidos if categorias_dict.get(cod) == "Chassi"]
                        if len(chassis_edicao) == 0:
                            st.error("❌ É obrigatório manter exatamente 1 chassi na prescrição.")
                        elif len(chassis_edicao) > 1:
                            st.error(f"❌ Foram selecionados {len(chassis_edicao)} chassis. É permitido apenas 1 chassi.")
                        elif erro_edicao_notas:
                            st.error("❌ Corrija as preferências repetidas antes de recalcular.")
                        else:
                            with st.spinner("Recalculando com os novos parâmetros..."):
                                st_plim, c_plim, q_plim, f_plim, df_d_plim = resolver_plim(
                                    novos_itens_escolhidos, novo_lambda, novo_orcamento, mapa_edicao_qualidade
                                )
                                st_fb, c_fb, q_fb, f_fb, df_d_fb, _, _, _ = resolver_forca_bruta(
                                    novos_itens_escolhidos, novo_lambda, novo_orcamento, mapa_edicao_qualidade
                                )

                                atualizar_prescricao_existente(
                                    id_prescricao=id_selecionado,
                                    novo_nome_paciente=novo_nome.strip(),
                                    novos_itens_ids=novos_itens_escolhidos,
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
                                    mapa_qualidade_item=mapa_edicao_qualidade
                                )

                            st.success(f"Prescrição {id_selecionado} atualizada e recalculada com sucesso.")
                            st.rerun()
