# --- Para executar este código, abra o terminal no PyCharm e digite:
# --- streamlit run dash-tcm3.3.py
# --- Para encerrar a execução: ctrl + c

import streamlit as st
import pandas as pd
import pulp
import json
import unicodedata
import os
import itertools
import time
import re
from datetime import datetime

# Configuração da página do Streamlit
st.set_page_config(layout="wide", page_title="TCM 3.3 - Prescrição Customizada e Otimização")

ARQUIVO_PRESC_SALVAS = "dataset-prescricoes-manuais.json"


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


PONTOS_QUALIDADE = {"Fornecedor-A": 3, "Fornecedor-B": 2, "Fornecedor-C": 1}


# ==========================================
# CARGA DO CATÁLOGO DE COMPONENTES
# ==========================================
@st.cache_data
def carregar_catalogo():
    path_ds7 = "dataset_7_componentes.json"
    if not os.path.exists(path_ds7):
        st.error(f"Arquivo '{path_ds7}' não encontrado no diretório de execução.")
        st.stop()

    with open(path_ds7, "r", encoding="utf-8") as f:
        ds7 = json.load(f)

    catmat_dict = {}
    descricoes_oficiais = {}
    categorias_dict = {}

    for comp in ds7['componentes']:
        id_comp = comp["id_componente"]
        forn = comp["fornecedor"]
        preco = float(comp.get("preco_max_BRL", 0))

        if id_comp not in catmat_dict:
            catmat_dict[id_comp] = {}
            descricoes_oficiais[id_comp] = comp.get("descricao_oficial", "")
            categorias_dict[id_comp] = comp.get("categoria", "Outros")
        catmat_dict[id_comp][forn] = preco

    return catmat_dict, descricoes_oficiais, categorias_dict


catmat_dict, descricoes_oficiais, categorias_dict = carregar_catalogo()


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
    "Bandagem de fixação": "CATMAT-478132"
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


def salvar_nova_prescricao(id_prescricao, nome_paciente, itens_ids, lambda_val, orcamento_val,
                           status_plim, custo_plim, qual_plim, fo_plim, df_det_plim,
                           status_fb, custo_fb, qual_fb, fo_fb, df_det_fb,
                           modo_entrada):
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
        "detalhes_plim": df_det_plim.to_dict(orient="records"),
        "detalhes_fb": df_det_fb.to_dict(orient="records")
    }
    prescricoes = [p for p in prescricoes if p["id_prescricao"] != id_prescricao]
    prescricoes.insert(0, registro)
    with open(ARQUIVO_PRESC_SALVAS, "w", encoding="utf-8") as f:
        json.dump(prescricoes, f, ensure_ascii=False, indent=2)


def atualizar_prescricao_existente(id_prescricao, novo_nome_paciente, novos_itens_ids, lambda_val, orcamento_val,
                                   status_plim, custo_plim, qual_plim, fo_plim, df_det_plim,
                                   status_fb, custo_fb, qual_fb, fo_fb, df_det_fb):
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
def resolver_plim(itens_prescritos, lambda_param, limite_orcamento):
    itens_validos = [k for k in itens_prescritos if k in catmat_dict]
    if not itens_validos:
        return "Inviável - Itens ausentes", 0.0, 0.0, None, pd.DataFrame()

    n_itens = len(itens_validos)
    custo_max_poss = sum(max(catmat_dict[k].values()) for k in itens_validos)
    qual_max_poss = n_itens * max(PONTOS_QUALIDADE.values())

    m = pulp.LpProblem("PLIM_Manual", pulp.LpMinimize)
    x = {(idx, k, f): pulp.LpVariable(f"x_{idx}_{k}_{f}", cat="Binary")
         for idx, k in enumerate(itens_validos) for f in catmat_dict[k].keys()}
    qp = pulp.LpVariable("qp", lowBound=0, cat="Continuous")

    custo_total = pulp.lpSum(
        x[idx, k, f] * catmat_dict[k][f] for idx, k in enumerate(itens_validos) for f in catmat_dict[k].keys())
    qualidade_total = pulp.lpSum(
        x[idx, k, f] * PONTOS_QUALIDADE[f] for idx, k in enumerate(itens_validos) for f in catmat_dict[k].keys())

    custo_norm = custo_total / custo_max_poss if custo_max_poss > 0 else custo_total
    qual_norm = qp / qual_max_poss if qual_max_poss > 0 else qp

    m += lambda_param * custo_norm - (1 - lambda_param) * qual_norm
    for idx, k in enumerate(itens_validos):
        m += pulp.lpSum(x[idx, k, f] for f in catmat_dict[k].keys()) == 1
    m += custo_total <= limite_orcamento
    m += qp == qualidade_total

    m.solve(pulp.PULP_CBC_CMD(msg=0))

    detalhes = []
    if pulp.LpStatus[m.status] == "Optimal":
        status = "Otimizado"
        custo = pulp.value(custo_total)
        qualidade = pulp.value(qp)
        fo = pulp.value(m.objective)
        for idx, k in enumerate(itens_validos):
            for f in catmat_dict[k].keys():
                if round(pulp.value(x[idx, k, f])) == 1:
                    detalhes.append({
                        "Componente": k,
                        "Fornecedor Escolhido": f,
                        "Valor do Item": catmat_dict[k][f],
                        "Pontos Qualidade": PONTOS_QUALIDADE[f]
                    })
    else:
        status = f"Excedeu {formatar_moeda(limite_orcamento)}"
        custo = 0.0
        qualidade = 0.0
        fo = None
        for k in itens_validos:
            f_min = min(catmat_dict[k], key=lambda f: catmat_dict[k][f])
            custo += catmat_dict[k][f_min]
            qualidade += PONTOS_QUALIDADE[f_min]
            detalhes.append({
                "Componente": k,
                "Fornecedor Escolhido": f_min,
                "Valor do Item": catmat_dict[k][f_min],
                "Pontos Qualidade": PONTOS_QUALIDADE[f_min]
            })

    return status, custo, qualidade, fo, pd.DataFrame(detalhes)


def resolver_forca_bruta(itens_prescritos, lambda_param, limite_orcamento):
    itens_validos = [k for k in itens_prescritos if k in catmat_dict]
    if not itens_validos:
        return "Inviável - Itens ausentes", 0.0, 0.0, None, pd.DataFrame(), 0, 0.0, "0 = 0"

    t0 = time.time()
    n_itens = len(itens_validos)
    custo_max_poss = sum(max(catmat_dict[k].values()) for k in itens_validos)
    qual_max_poss = n_itens * max(PONTOS_QUALIDADE.values())

    opcoes_fornecedores = [list(catmat_dict[k].keys()) for k in itens_validos]
    todas_comb = list(itertools.product(*opcoes_fornecedores))
    total_combinacoes = len(todas_comb)

    melhor_fo = float("inf")
    melhor_comb = None
    melhor_custo = 0.0
    melhor_qual = 0.0

    for comb in todas_comb:
        custo_comb = sum(catmat_dict[k][f] for k, f in zip(itens_validos, comb))
        if custo_comb <= limite_orcamento:
            qual_comb = sum(PONTOS_QUALIDADE[f] for f in comb)
            c_norm = custo_comb / custo_max_poss if custo_max_poss > 0 else custo_comb
            q_norm = qual_comb / qual_max_poss if qual_max_poss > 0 else qual_comb
            fo_comb = lambda_param * c_norm - (1 - lambda_param) * q_norm

            if fo_comb < melhor_fo:
                melhor_fo = fo_comb
                melhor_comb = comb
                melhor_custo = custo_comb
                melhor_qual = qual_comb

    detalhes = []
    if melhor_comb is not None:
        status = "Otimizado"
        for k, f in zip(itens_validos, melhor_comb):
            detalhes.append({
                "Componente": k,
                "Fornecedor Escolhido": f,
                "Valor do Item": catmat_dict[k][f],
                "Pontos Qualidade": PONTOS_QUALIDADE[f]
            })
    else:
        status = f"Excedeu {formatar_moeda(limite_orcamento)}"
        melhor_custo = 0.0
        melhor_qual = 0.0
        melhor_fo = None
        for k in itens_validos:
            f_min = min(catmat_dict[k], key=lambda f: catmat_dict[k][f])
            melhor_custo += catmat_dict[k][f_min]
            melhor_qual += PONTOS_QUALIDADE[f_min]
            detalhes.append({
                "Componente": k,
                "Fornecedor Escolhido": f_min,
                "Valor do Item": catmat_dict[k][f_min],
                "Pontos Qualidade": PONTOS_QUALIDADE[f_min]
            })

    tempo_exec = time.time() - t0
    racional_calculo = " × ".join(
        [str(len(op)) for op in opcoes_fornecedores]) + f" = {formatar_inteiro(total_combinacoes)}"

    return status, melhor_custo, melhor_qual, melhor_fo, pd.DataFrame(
        detalhes), total_combinacoes, tempo_exec, racional_calculo


# ==========================================
# INTERFACE STREAMLIT (UI)
# ==========================================
st.title("♿ TCM 3.3 - Entrada de Prescrição por Categorias & Otimização")
st.markdown(
    "Prescrição customizada com base nas **7 Categorias da Dissertação** e resolução simultânea via **PLIM** e **Força Bruta**.")

tab_nova, tab_historico = st.tabs(["📝 Nova Prescrição & Otimização", "📂 Histórico de Prescrições Salvas"])

with tab_nova:
    st.sidebar.header("🛠️ Parâmetros de Otimização")
    LAMBDA = st.sidebar.slider(
        "Fator de Balanceamento (λ):",
        0.0, 1.0, 0.2, 0.1,
        help="Define o equilíbrio matemático entre custo total e nível de qualidade técnica."
    )

    peso_custo = int(round(LAMBDA * 100))
    peso_qualidade = int(round((1 - LAMBDA) * 100))

    col_p1, col_p2 = st.sidebar.columns(2)
    col_p1.metric("Peso Qualidade", f"{peso_qualidade}%")
    col_p2.metric("Peso Economia", f"{peso_custo}%")

    # if LAMBDA == 0.0:
    #     st.sidebar.info("Prioridade: Qualidade Máxima Absoluta. Foco integral no Fornecedor-A, sem penalidade de custo.")
    # elif LAMBDA <= 0.3:
    #     st.sidebar.info("Prioridade: Alta Qualidade. Favorece componentes com maior pontuação técnica, buscando custos menores como critério secundário.")
    # elif LAMBDA <= 0.7:
    #     st.sidebar.info("Prioridade: Balanceada. Equilíbrio proporcional entre pontuação técnica dos fornecedores e economia orçamentária.")
    # elif LAMBDA < 1.0:
    #     st.sidebar.info("Prioridade: Economia Financeira. Busca ativamente preços menores, aceitando fornecedores de menor pontuação técnica.")
    # else:
    #     st.sidebar.info("Prioridade: Mínimo Custo Absoluto. Foco exclusivo no menor preço, desconsiderando pontos de qualidade.")

    LIMITE_ORCAMENTO = st.sidebar.number_input("Limite Orçamentário (R$)", min_value=500.0, value=10000.0, step=500.0)

    # Identificação Única da Prescrição e do Paciente
    col_id1, col_id2 = st.columns([1, 1])
    id_sugestao = f"PRESC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    paciente_sugestao = obter_proximo_identificador_paciente()

    with col_id1:
        id_prescricao_input = st.text_input("Identificador Único da Prescrição (ID):", value=id_sugestao)
    with col_id2:
        nome_paciente_input = st.text_input(
            "Nome do Paciente / Responsável:",
            value=paciente_sugestao,
            help="Identificador sequencial pré-preenchido automaticamente a partir da base existente."
        )

    modo_entrada = st.radio("Selecione o modo de montagem da prescrição:",
                            ["Guia Clínico Estruturado (7 Categorias da Dissertação)",
                             "Seleção Direta por Componentes do Catálogo"], horizontal=True)

    itens_selecionados_ids = []

    if modo_entrada == "Guia Clínico Estruturado (7 Categorias da Dissertação)":
        st.info(
            "💡 Preencha os componentes clínicos agrupados segundo as 7 categorias técnicas da dissertação.")

        c_col1, c_col2 = st.columns(2)

        with c_col1:
            # 1. Chassi
            st.subheader("1. Chassi")
            check_chassi_relax = st.checkbox("Chassi RELAX (Recliner Independente + Tilt)", value=False)
            check_chassi_prisma = st.checkbox("Chassi PRISMA (Tilt do Conjunto Assento/Encosto)", value=False)
            if check_chassi_relax: itens_selecionados_ids.append(
                MAPEAMENTO_CLINICO["Chassi RELAX (Recliner Independente + Tilt)"])
            if check_chassi_prisma: itens_selecionados_ids.append(
                MAPEAMENTO_CLINICO["Chassi PRISMA (Tilt do Conjunto Assento/Encosto)"])

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
            if check_tronco: itens_selecionados_ids.append(
                MAPEAMENTO_CLINICO["Apoio de tronco (Estabilizadores laterais)"])
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
        st.info("💡 Selecione diretamente os componentes e peças técnicas catalogadas no dataset.")
        todos_componentes = list(catmat_dict.keys())
        itens_selecionados_ids = st.multiselect(
            "Selecione os componentes do catálogo para compor a cadeira:",
            options=todos_componentes,
            default=[],
            format_func=formatar_opcao_catalogo,
            help="Pesquise por código CATMAT, categoria técnica ou termos da descrição oficial."
        )

    itens_selecionados_ids = list(dict.fromkeys(itens_selecionados_ids))

    st.divider()

    st.subheader(f"📋 Resumo dos Componentes Prescritos ({len(itens_selecionados_ids)} itens)")
    if itens_selecionados_ids:
        tabela_itens_resumo = []
        for cod in itens_selecionados_ids:
            qtd_forn = len(catmat_dict.get(cod, {}).keys())
            forn_nomes = ", ".join(list(catmat_dict.get(cod, {}).keys()))
            tabela_itens_resumo.append({
                "Código do Componente": cod,
                "Categoria (Tabela 6)": categorias_dict.get(cod, "N/A"),
                "Descrição Oficial": descricoes_oficiais.get(cod, "Descrição não disponível"),
                "Fornecedores Homologados": forn_nomes,
                "Qtd. Opções": qtd_forn
            })
        st.dataframe(pd.DataFrame(tabela_itens_resumo), use_container_width=True)
    else:
        st.warning("Nenhum componente selecionado. Marque ao menos um componente.")

    if st.button("🚀 Otimizar e Salvar Prescrição", type="primary"):
        nome_paciente_final = nome_paciente_input.strip()

        if not nome_paciente_final:
            st.error("O campo 'Nome do Paciente / Responsável' não pode ficar em branco.")
            st.stop()

        if not itens_selecionados_ids:
            st.error("Selecione ao menos um componente antes de otimizar.")
            st.stop()

        if existe_paciente_na_base(nome_paciente_final):
            st.error(
                f"O identificador '{nome_paciente_final}' já existe em '{ARQUIVO_PRESC_SALVAS}'. Por favor, utilize um número/código sequencial diferente.")
            st.stop()

        with st.spinner("A resolver os modelos de otimização e a persistir o registro..."):
            status_plim, custo_plim, qual_plim, fo_plim, df_det_plim = resolver_plim(
                itens_selecionados_ids, LAMBDA, LIMITE_ORCAMENTO
            )

            status_fb, custo_fb, qual_fb, fo_fb, df_det_fb, total_comb_fb, tempo_fb, racional_espaco = resolver_forca_bruta(
                itens_selecionados_ids, LAMBDA, LIMITE_ORCAMENTO
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
                modo_entrada=modo_entrada
            )

        st.success(
            f"Prescrição {id_prescricao_input} ({nome_paciente_final}) otimizada e salva com sucesso em {ARQUIVO_PRESC_SALVAS}.")

        st.header("📊 Resultado Consolidado: Solver (PLIM) vs. Força Bruta (FB)")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status da Solução", f"{status_plim} (PLIM)", f"{status_fb} (FB)")
        c2.metric("Custo Total", formatar_moeda(custo_plim), f"FB: {formatar_moeda(custo_fb)}")
        c3.metric("Qualidade Total", f"{qual_plim:.1f} pts", f"FB: {qual_fb:.1f} pts")
        fo_plim_str = f"{fo_plim:.4f}" if fo_plim is not None else "N/A"
        fo_fb_str = f"{fo_fb:.4f}" if fo_fb is not None else "N/A"
        c4.metric("Valor Função Objetivo", fo_plim_str, f"FB: {fo_fb_str}")

        st.info(
            f"🔍 **Espaço de Busca Exaustivo:** `{formatar_inteiro(total_comb_fb)}` combinações avaliadas em `{tempo_fb:.4f}` segundos.\n\n"
            f"**Racional Multiplicativo:** `{racional_espaco}`")

        diff_fo = abs(fo_plim - fo_fb) if (fo_plim is not None and fo_fb is not None) else 0.0
        if diff_fo < 1e-4 and status_plim == status_fb:
            st.success(
                "Ótimo Global Comprovado: O solver PLIM convergiu exatamente para a mesma solução ótima obtida pela busca exaustiva.")
        else:
            st.warning(f"Atenção: Detectada divergência matemática entre os métodos (ΔFO = {diff_fo:.6f}).")

        st.subheader("🔍 Comparativo de Escolha por Componente (Lado a Lado)")
        df_comp = pd.merge(
            df_det_plim,
            df_det_fb,
            on="Componente",
            suffixes=(" (PLIM)", " (FB)")
        )
        st.dataframe(
            df_comp.style.format({
                "Valor do Item (PLIM)": formatar_moeda,
                "Valor do Item (FB)": formatar_moeda
            }),
            use_container_width=True
        )

# ==========================================
# ABA: HISTÓRICO DE PRESCRIÇÕES SALVAS
# ==========================================
with tab_historico:
    st.header("📂 Gerenciamento de Prescrições (Visualizar / Alterar / Excluir)")
    historico = carregar_prescricoes_salvas()

    if not historico:
        st.info("Nenhuma prescrição manual foi salva até o momento.")
    else:
        df_hist = pd.DataFrame(historico)
        colunas_exibir = ["id_prescricao", "data_hora", "nome_paciente", "total_itens", "status_otimizacao",
                          "custo_total", "qualidade_total", "valor_fo", "lambda", "limite_orcamento"]

        for c in colunas_exibir:
            if c not in df_hist.columns:
                df_hist[c] = None

        df_hist_vis = df_hist[colunas_exibir].rename(columns={
            "id_prescricao": "ID Prescrição",
            "data_hora": "Data/Hora",
            "nome_paciente": "Paciente / Responsável",
            "total_itens": "Qtd. Itens",
            "status_otimizacao": "Status",
            "custo_total": "Custo Total",
            "qualidade_total": "Qualidade",
            "valor_fo": "Valor FO",
            "lambda": "λ",
            "limite_orcamento": "Orçamento Máx."
        })

        st.dataframe(
            df_hist_vis.style.format({
                "Custo Total": formatar_moeda,
                "Orçamento Máx.": formatar_moeda,
                "Qualidade": "{:.1f} pts",
                "Valor FO": lambda x: f"{x:.4f}" if pd.notna(x) else "N/A",
                "λ": "{:.2f}"
            }),
            use_container_width=True
        )

        json_bytes = json.dumps(historico, ensure_ascii=False, indent=2).encode('utf-8')
        st.download_button(
            label="📥 Baixar Base Completa de Prescrições (.json)",
            data=json_bytes,
            file_name=ARQUIVO_PRESC_SALVAS,
            mime="application/json"
        )

        st.divider()
        st.subheader("🛠️ Detalhes e Gerenciamento da Prescrição")

        opcoes_presc = [f"{p['id_prescricao']} | {p['nome_paciente']} ({p['data_hora']})" for p in historico]
        escolha = st.selectbox("Selecione a prescrição que deseja gerenciar:", opcoes_presc)

        if escolha:
            id_selecionado = escolha.split(" | ")[0]
            presc_detalhe = next(p for p in historico if p["id_prescricao"] == id_selecionado)

            c_info1, c_info2 = st.columns([3, 1])
            with c_info1:
                st.markdown(
                    f"**ID:** `{presc_detalhe['id_prescricao']}` | **Paciente:** `{presc_detalhe['nome_paciente']}`")
                st.markdown(
                    f"**Data de Criação:** {presc_detalhe['data_hora']} | **Modo de Criação:** {presc_detalhe.get('modo_entrada', 'N/A')}")
                st.markdown(
                    f"**Custo Total:** `{formatar_moeda(presc_detalhe['custo_total'])}` | **Qualidade:** `{presc_detalhe['qualidade_total']:.1f} pts` | **Status:** `{presc_detalhe['status_otimizacao']}`")

            with c_info2:
                if st.button("🗑️ Excluir Prescrição", key=f"btn_del_{id_selecionado}", type="secondary"):
                    excluir_prescricao_salva(id_selecionado)
                    st.warning(f"Prescrição {id_selecionado} excluída com sucesso.")
                    st.rerun()

            # Obtenção dos dataframes para montagem do comparativo lado a lado
            if "detalhes_plim" in presc_detalhe and "detalhes_fb" in presc_detalhe:
                df_det_plim_hist = pd.DataFrame(presc_detalhe["detalhes_plim"])
                df_det_fb_hist = pd.DataFrame(presc_detalhe["detalhes_fb"])
            else:
                lam = float(presc_detalhe.get("lambda", 0.2))
                orc = float(presc_detalhe.get("limite_orcamento", 10000.0))
                _, _, _, _, df_det_plim_hist = resolver_plim(presc_detalhe["itens_prescritos"], lam, orc)
                _, _, _, _, df_det_fb_hist, _, _, _ = resolver_forca_bruta(presc_detalhe["itens_prescritos"], lam, orc)

            st.markdown("### 🔍 Comparativo de Escolha por Componente (Lado a Lado)")
            if not df_det_plim_hist.empty and not df_det_fb_hist.empty:
                df_comp_hist = pd.merge(
                    df_det_plim_hist,
                    df_det_fb_hist,
                    on="Componente",
                    suffixes=(" (PLIM)", " (FB)")
                )
                st.dataframe(
                    df_comp_hist.style.format({
                        "Valor do Item (PLIM)": formatar_moeda,
                        "Valor do Item (FB)": formatar_moeda,
                        "Pontos Qualidade (PLIM)": "{:.0f}",
                        "Pontos Qualidade (FB)": "{:.0f}"
                    }),
                    use_container_width=True
                )
            else:
                st.warning("Não há dados de detalhamento por componente para esta prescrição.")

            with st.expander("✏️ Editar e Reotimizar esta Prescrição"):
                st.markdown(f"Você está editando a prescrição **{id_selecionado}**.")

                col_ed1, col_ed2 = st.columns(2)
                with col_ed1:
                    novo_nome = st.text_input("Identificador do Paciente:", value=presc_detalhe["nome_paciente"],
                                              key=f"ed_nome_{id_selecionado}")
                    novo_lambda = st.slider("Peso Custo vs. Qualidade (λ):", 0.0, 1.0,
                                            float(presc_detalhe.get("lambda", 0.2)), 0.1,
                                            key=f"ed_lam_{id_selecionado}")
                with col_ed2:
                    novo_orcamento = st.number_input("Limite Orçamentário (R$):", min_value=500.0,
                                                     value=float(presc_detalhe.get("limite_orcamento", 10000.0)),
                                                     step=500.0, key=f"ed_orc_{id_selecionado}")

                todos_itens_cat = list(catmat_dict.keys())
                itens_atuais_validos = [i for i in presc_detalhe["itens_prescritos"] if i in catmat_dict]

                novos_itens_escolhidos = st.multiselect(
                    "Componentes da Prescrição (adicione ou remova itens):",
                    options=todos_itens_cat,
                    default=itens_atuais_validos,
                    format_func=formatar_opcao_catalogo,
                    key=f"ed_itens_{id_selecionado}",
                    help="Pesquise por código CATMAT, categoria técnica ou termos da descrição oficial."
                )

                if st.button("💾 Salvar Alterações e Reotimizar", key=f"btn_save_edit_{id_selecionado}",
                             type="primary"):
                    if not novo_nome.strip():
                        st.error("O identificador do paciente não pode ficar em branco.")
                    elif existe_paciente_na_base(novo_nome, id_ignorar=id_selecionado):
                        st.error(f"O identificador '{novo_nome}' já pertence a outra prescrição cadastrada.")
                    elif not novos_itens_escolhidos:
                        st.error("A prescrição deve conter ao menos um componente.")
                    else:
                        with st.spinner("Reotimizando a prescrição alterada..."):
                            st_plim, c_plim, q_plim, f_plim, df_d_plim = resolver_plim(
                                novos_itens_escolhidos, novo_lambda, novo_orcamento
                            )
                            st_fb, c_fb, q_fb, f_fb, df_d_fb, _, _, _ = resolver_forca_bruta(
                                novos_itens_escolhidos, novo_lambda, novo_orcamento
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
                                df_det_fb=df_d_fb
                            )

                        st.success(f"Prescrição {id_selecionado} atualizada e reotimizada com sucesso.")
                        st.rerun()