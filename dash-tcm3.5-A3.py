# --- Para executar este código, abra o terminal no PyCharm e digite:
# --- streamlit run dash-tcm3.5-A3.py
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
    layout="wide", page_title="TCM 3.5-A3 - Prescrição e Otimização Customizada"
)

ARQUIVO_PRESC_SALVAS = "dataset-prescricoes-manuais.json"


# ==========================================
# FUNÇÕES DE FORMATAÇÃO E NORMALIZAÇÃO
# ==========================================
def formatar_moeda(valor):
  if pd.isna(valor):
    return "R$ 0,00"
  return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace(
      "X", "."
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
  if pd.isna(valor):
    return "0"
  return f"{int(valor):,}".replace(",", ".")


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
    "Chassi RELAX (Recliner Independente + Tilt)": (
        "CHASSI-RELAX"
        if "CHASSI-RELAX" in catmat_dict
        else "CATMAT-400780"
    ),
    "Chassi PRISMA (Tilt do Conjunto Assento/Encosto)": (
        "CHASSI-PRISMA"
        if "CHASSI-PRISMA" in catmat_dict
        else "CATMAT-623881"
    ),
    # 2. Almofada_Assento
    "Assento anatômico com onda": (
        "ALM-ONDA-INF"
        if "ALM-ONDA-INF" in catmat_dict
        else "CATMAT-483711"
    ),
    "Assento plano": (
        "ALM-PLANA-INF"
        if "ALM-PLANA-INF" in catmat_dict
        else "CATMAT-446695"
    ),
    "Assento com faixas": "CATMAT-446695",
    # 3. Suporte_Cabeca
    "Apoio de cabeça curvado": (
        "SUP-CAB-CURV"
        if "SUP-CAB-CURV" in catmat_dict
        else "CATMAT-600560"
    ),
    "Apoio de cabeça occipital": "CATMAT-600560",
    # 4. Suporte_Postural
    "Encosto plano": (
        "CATMAT-455920"
        if "CATMAT-455920" in catmat_dict
        else "CATMAT-455891"
    ),
    "Apoio de tronco (Estabilizadores laterais)": (
        "CATMAT-455920"
        if "CATMAT-455920" in catmat_dict
        else "CATMAT-455888"
    ),
    "Cinto peitoral": (
        "ACC-CINTO-PEITORAL"
        if "ACC-CINTO-PEITORAL" in catmat_dict
        else "CATMAT-477255"
    ),
    "Cinto pélvico": (
        "CATMAT-474765"
        if "CATMAT-474765" in catmat_dict
        else "CATMAT-477257"
    ),
    "Apoio de quadril": (
        "ACC-QUADRIL"
        if "ACC-QUADRIL" in catmat_dict
        else "CATMAT-454732"
    ),
    "Abdutor removível": (
        "ACC-ABDUTOR-REM"
        if "ACC-ABDUTOR-REM" in catmat_dict
        else "CATMAT-455901"
    ),
    "Adutor removível": (
        "ACC-ADUTOR-REM"
        if "ACC-ADUTOR-REM" in catmat_dict
        else "CATMAT-455902"
    ),
    # 5. Apoio_Ajustavel
    "Apoio de braços": (
        "ACC-BRACO-GEN"
        if "ACC-BRACO-GEN" in catmat_dict
        else "CATMAT-400802"
    ),
    "Apoio de pés plástico": (
        "CATMAT-400779"
        if "CATMAT-400779" in catmat_dict
        else "CATMAT-400778"
    ),
    "Apoio de pés caixa em madeira": (
        "ACC-PES-CX-MAD"
        if "ACC-PES-CX-MAD" in catmat_dict
        else "CATMAT-400796"
    ),
    "Apoio de panturrilha": "CATMAT-445967",
    "Mesa de atividades": "CATMAT-409985",
    "Suporte de dieta": (
        "ACC-SUP-DIETA"
        if "ACC-SUP-DIETA" in catmat_dict
        else "CATMAT-438188"
    ),
    # 6. Imobilizador
    "Bloqueador de joelhos": (
        "CATMAT-452106"
        if "CATMAT-452106" in catmat_dict
        else "CATMAT-452113"
    ),
    "Posicionador de punho (Órtese)": "CATMAT-452082",
    "Faixa restringidora postural": "CATMAT-452097",
    # 7. Fixador
    "Faixa p/ pés e tornozelos": (
        "CATMAT-482135"
        if "CATMAT-482135" in catmat_dict
        else "CATMAT-445967"
    ),
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
    id_prescricao,
    nome_paciente,
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
    modo_entrada,
    mapa_qualidade_item,
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
    id_prescricao,
    novo_nome_paciente,
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
    mapa_qualidade_item,
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
def resolver_plim(
    itens_prescritos, lambda_param, limite_orcamento, mapa_qualidade
):
  itens_validos = [k for k in itens_prescritos if k in catmat_dict]
  if not itens_validos:
    return "Inviável - Itens ausentes", 0.0, 0.0, None, pd.DataFrame()

  n_itens = len(itens_validos)
  custo_max_poss = float(
      sum(max(catmat_dict[k].values()) for k in itens_validos)
  )

  # Qualidade máxima possível baseada na nota mais alta atribuída por componente
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
      var_name = f"x_{idx}_{f}".replace("-", "_").replace(" ", "_")
      x[(idx, k, f)] = pulp.LpVariable(var_name, cat=pulp.LpBinary)

  custo_total = pulp.lpSum(
      x[idx, k, f] * float(catmat_dict[k][f])
      for idx, k in enumerate(itens_validos)
      for f in catmat_dict[k].keys()
  )

  qualidade_total = pulp.lpSum(
      x[idx, k, f] * float(mapa_qualidade.get(k, {}).get(f, 1)) # A nota é buscada no par [k][f], ou seja, a nota do fornecedor f especificamente para o componente k
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

  detalhes = []
  if pulp.LpStatus[m.status] == "Optimal":
    status = "Otimizado"
    custo = float(pulp.value(custo_total))
    qualidade = float(pulp.value(qualidade_total))
    fo = float(pulp.value(m.objective))
    for idx, k in enumerate(itens_validos):
      for f in catmat_dict[k].keys():
        if round(pulp.value(x[idx, k, f])) == 1:
          nota_f = mapa_qualidade.get(k, {}).get(f, 1)
          detalhes.append({
              "Componente": k,
              "Fornecedor Escolhido": f,
              "Valor do Item": catmat_dict[k][f],
              "Pontos Qualidade": nota_f,
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
          "Fornecedor Escolhido": f_min,
          "Valor do Item": catmat_dict[k][f_min],
          "Pontos Qualidade": mapa_qualidade.get(k, {}).get(f_min, 1),
      })

  return status, custo, qualidade, fo, pd.DataFrame(detalhes)


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

# Soma a nota máxima disponível de cada componente individualmente
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

  melhor_fo = float("inf")
  melhor_comb = None
  melhor_custo = 0.0
  melhor_qual = 0.0

  for comb in itertools.product(*opcoes_fornecedores):
    custo_comb = sum(catmat_dict[k][f] for k, f in zip(itens_validos, comb))
    if custo_comb <= limite_orcamento:
      # A avaliação pareia cada componente k com seu respectivo fornecedor f
      qual_comb = sum(mapa_qualidade.get(k, {}).get(f, 1) for k, f in zip(itens_validos, comb))
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
          "Pontos Qualidade": mapa_qualidade.get(k, {}).get(f, 1),
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
          "Fornecedor Escolhido": f_min,
          "Valor do Item": catmat_dict[k][f_min],
          "Pontos Qualidade": mapa_qualidade.get(k, {}).get(f_min, 1),
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
st.title("♿ TCM 3.5-A3 - Prescrição Customizada & Otimização")
st.markdown(
    "Prescrição estruturada segundo as **7 Categorias da Dissertação** com"
    " qualificação técnica direta por componente e otimização biobjetivo (**PLIM** vs."
    " **Força Bruta**)."
)

# ----------------------------------------------------
# BARRA LATERAL (PARÂMETROS DE OTIMIZAÇÃO)
# ----------------------------------------------------
st.sidebar.header("🛠️ Parâmetros de Otimização")

LAMBDA = st.sidebar.slider(
    "Fator de Priorização (λ):",
    0.0,
    1.0,
    0.2,
    0.1,
    help=(
        "Define o equilíbrio matemático entre foco orçamentário e prioridade"
        " técnica."
    ),
)

perc_economia = int(round(LAMBDA * 100))
perc_qualidade = int(round((1 - LAMBDA) * 100))

col_p1, col_p2 = st.sidebar.columns(2)
col_p1.metric("Prioridade Técnica", f"{perc_qualidade}%")
col_p2.metric("Foco Orçamentário", f"{perc_economia}%")

LIMITE_ORCAMENTO = st.sidebar.number_input(
    "Limite Orçamentário (R$):", min_value=500.0, value=10000.0, step=500.0
)

# ----------------------------------------------------
# NAVEGAÇÃO POR ABAS
# ----------------------------------------------------
tab_nova, tab_historico = st.tabs(
    ["📝 Nova Prescrição & Otimização", "📂 Histórico de Prescrições Salvas"]
)

# ----------------------------------------------------
# ABA 1: NOVA PRESCRIÇÃO & OTIMIZAÇÃO
# ----------------------------------------------------
with tab_nova:
  col_id1, col_id2 = st.columns([1, 1])
  id_sugestao = f"PRESC-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
  paciente_sugestao = obter_proximo_identificador_paciente()

  with col_id1:
    id_prescricao_input = st.text_input(
        "Identificador Único da Prescrição (ID):", value=id_sugestao
    )
  with col_id2:
    nome_paciente_input = st.text_input(
        "Nome do Paciente / Responsável:",
        value=paciente_sugestao,
        help="Identificador sequencial pré-preenchido automaticamente a partir da base existente.",
    )

  modo_entrada = st.radio(
      "Selecione o modo de montagem da prescrição:",
      [
          "Guia Clínico Estruturado (7 Categorias da Dissertação)",
          "Seleção Direta por Componentes do Catálogo",
      ],
      horizontal=True,
  )

  itens_selecionados_ids = []

  if modo_entrada == "Guia Clínico Estruturado (7 Categorias da Dissertação)":
    st.info(
        "💡 Preencha os componentes clínicos agrupados segundo as 7 categorias"
        " técnicas da dissertação."
    )

    c_col1, c_col2 = st.columns(2)

    with c_col1:
      # 1. Chassi (Seleção obrigatória e unívoca de Chassi)
      st.subheader("1. Chassi (Seleção Obrigatória e Única)")
      opcao_chassi = st.radio(
          "Selecione o Chassi da cadeira:",
          options=[
              "Chassi RELAX (Recliner Independente + Tilt)",
              "Chassi PRISMA (Tilt do Conjunto Assento/Encosto)",
          ],
          index=0,
          help=(
              "A cadeira deve obrigatoriamente possuir um chassi, sendo"
              " permitido selecionar apenas um modelo estrutural."
          ),
      )
      itens_selecionados_ids.append(MAPEAMENTO_CLINICO[opcao_chassi])

      # 2. Almofada_Assento
      st.subheader("2. Almofada do Assento")
      check_assento_onda = st.checkbox(
          "Assento anatômico com onda", value=False
      )
      check_assento_plano = st.checkbox("Assento plano", value=False)
      check_assento_faixas = st.checkbox("Assento com faixas", value=False)
      if check_assento_onda:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Assento anatômico com onda"]
        )
      if check_assento_plano:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Assento plano"])
      if check_assento_faixas:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Assento com faixas"])

      # 3. Suporte_Cabeca
      st.subheader("3. Suporte de Cabeça")
      check_cab_curv = st.checkbox("Apoio de cabeça curvado", value=False)
      check_cab_occip = st.checkbox("Apoio de cabeça occipital", value=False)
      if check_cab_curv:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Apoio de cabeça curvado"]
        )
      if check_cab_occip:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Apoio de cabeça occipital"]
        )

      # 4. Suporte_Postural
      st.subheader("4. Suporte Postural (Tronco e Pelve)")
      check_encosto = st.checkbox("Encosto plano", value=False)
      check_tronco = st.checkbox(
          "Apoio de tronco (Estabilizadores laterais)", value=False
      )
      check_peitoral = st.checkbox("Cinto peitoral", value=False)
      check_pelvico = st.checkbox("Cinto pélvico", value=False)
      check_quadril = st.checkbox("Apoio de quadril", value=False)
      check_abdutor = st.checkbox("Abdutor removível", value=False)
      check_adutor = st.checkbox("Adutor removível", value=False)

      if check_encosto:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Encosto plano"])
      if check_tronco:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Apoio de tronco (Estabilizadores laterais)"]
        )
      if check_peitoral:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Cinto peitoral"])
      if check_pelvico:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Cinto pélvico"])
      if check_quadril:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Apoio de quadril"])
      if check_abdutor:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Abdutor removível"])
      if check_adutor:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Adutor removível"])

    with c_col2:
      # 5. Apoio_Ajustavel
      st.subheader("5. Apoios Ajustáveis e Acessórios")
      check_braco = st.checkbox("Apoio de braços", value=False)
      check_pes = st.checkbox("Apoio de pés plástico", value=False)
      check_pes_mad = st.checkbox("Apoio de pés caixa em madeira", value=False)
      check_pant = st.checkbox("Apoio de panturrilha", value=False)
      check_mesa = st.checkbox("Mesa de atividades", value=False)
      check_dieta = st.checkbox("Suporte de dieta", value=False)

      if check_braco:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Apoio de braços"])
      if check_pes:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Apoio de pés plástico"]
        )
      if check_pes_mad:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Apoio de pés caixa em madeira"]
        )
      if check_pant:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Apoio de panturrilha"]
        )
      if check_mesa:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Mesa de atividades"])
      if check_dieta:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Suporte de dieta"])

      # 6. Imobilizador
      st.subheader("6. Imobilizadores e Contenção Rígida")
      check_bloq_joelho = st.checkbox("Bloqueador de joelhos", value=False)
      check_pos_punho = st.checkbox(
          "Posicionador de punho (Órtese)", value=False
      )
      check_faixa_rest = st.checkbox(
          "Faixa restringidora postural", value=False
      )

      if check_bloq_joelho:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Bloqueador de joelhos"]
        )
      if check_pos_punho:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Posicionador de punho (Órtese)"]
        )
      if check_faixa_rest:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Faixa restringidora postural"]
        )

      # 7. Fixador
      st.subheader("7. Fixadores e Bandagens")
      check_fx_pes_torn = st.checkbox(
          "Faixa p/ pés e tornozelos", value=False
      )
      check_fx_pes = st.checkbox("Faixa p/ pés", value=False)
      check_fx_torn = st.checkbox("Faixa p/ tornozelos", value=False)
      check_bandagem = st.checkbox("Bandagem de fixação", value=False)

      if check_fx_pes_torn:
        itens_selecionados_ids.append(
            MAPEAMENTO_CLINICO["Faixa p/ pés e tornozelos"]
        )
      if check_fx_pes:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Faixa p/ pés"])
      if check_fx_torn:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Faixa p/ tornozelos"])
      if check_bandagem:
        itens_selecionados_ids.append(MAPEAMENTO_CLINICO["Bandagem de fixação"])

  else:
    st.info(
        "💡 Selecione diretamente os componentes e peças técnicas catalogadas"
        " no dataset."
    )
    todos_componentes = list(catmat_dict.keys())
    itens_selecionados_ids = st.multiselect(
        "Selecione os componentes do catálogo para compor a cadeira:",
        options=todos_componentes,
        default=[],
        format_func=formatar_opcao_catalogo,
        help=(
            "Pesquise por código CATMAT, categoria técnica ou termos da"
            " descrição oficial."
        ),
    )

    chassis_no_catalogo = [
        cod
        for cod in itens_selecionados_ids
        if categorias_dict.get(cod) == "Chassi"
    ]
    if len(chassis_no_catalogo) == 0:
      st.warning(
          "⚠️ Atenção: É obrigatório selecionar exatamente 1 chassi estrutural"
          " no catálogo."
      )
    elif len(chassis_no_catalogo) > 1:
      st.error(
          "❌ Erro de Seleção: Foram selecionados"
          f" {len(chassis_no_catalogo)} chassis"
          f" ({', '.join(chassis_no_catalogo)}). Mantenha apenas 1 chassi."
      )

  itens_selecionados_ids = list(dict.fromkeys(itens_selecionados_ids))

  st.divider()

  # ====================================================
  # BLOCO DE QUALIFICAÇÃO TÉCNICA (FORNECEDORES POR ITEM)
  # ====================================================
  st.subheader("🎖️ Qualificação Técnica dos Fornecedores por Componente")
  st.markdown(
      "Para cada componente selecionado, atribua as notas técnicas de **1 a 3"
      " (sem notas repetidas)** aos respectivos fornecedores:"
  )

  mapa_qualidade_coletado = {}
  erro_notas_duplicadas = False
  componentes_com_erro = []

  padrao_inicial_notas = {"Fornecedor-A": 3, "Fornecedor-B": 2, "Fornecedor-C": 1}

  if itens_selecionados_ids:
    for cod_item in itens_selecionados_ids:
      desc_item = descricoes_oficiais.get(cod_item, "Sem descrição")
      cat_item = categorias_dict.get(cod_item, "Outros")
      fornecedores_item = list(catmat_dict.get(cod_item, {}).keys())

      with st.expander(
          f"📦 [{cat_item}] {cod_item} - {desc_item[:70]}...",
          expanded=True,
      ):
        st.caption(f"**Descrição Completa:** {desc_item}")
        cols_forn = st.columns(len(fornecedores_item))
        notas_item = {}

        for idx_f, forn in enumerate(fornecedores_item):
          preco_ref = catmat_dict[cod_item][forn]
          val_def = padrao_inicial_notas.get(forn, max(1, 3 - idx_f))

          with cols_forn[idx_f]:
            st.markdown(f"**{forn}**")
            st.markdown(f"Preço: `{formatar_moeda(preco_ref)}`")
            nota = st.selectbox(
                f"Escore Técnico ({forn}):",
                options=[3, 2, 1],
                index=[3, 2, 1].index(val_def) if val_def in [3, 2, 1] else 0,
                key=f"qual_{cod_item}_{forn}",
                help="Classifique o nível de qualidade técnica deste fornecedor para este item específico.",
            )
            notas_item[forn] = nota

        # Validação de unicidade no componente
        valores_notas_item = list(notas_item.values())
        if len(valores_notas_item) != len(set(valores_notas_item)):
          st.error(
              f"⚠️ Atenção em **{cod_item}**: Cada fornecedor deve receber uma"
              " nota distinta (1, 2 e 3). Não repita escores para o mesmo item."
          )
          erro_notas_duplicadas = True
          componentes_com_erro.append(cod_item)

        mapa_qualidade_coletado[cod_item] = notas_item
  else:
    st.info("Selecione componentes acima para configurar os fornecedores.")

  st.divider()

  st.subheader(
      f"📋 Resumo da Prescrição ({len(itens_selecionados_ids)} itens)"
  )
  if itens_selecionados_ids:
    tabela_itens_resumo = []
    for cod in itens_selecionados_ids:
      qtd_forn = len(catmat_dict.get(cod, {}).keys())
      det_forn = []
      for f in catmat_dict.get(cod, {}).keys():
        nota_atrib = mapa_qualidade_coletado.get(cod, {}).get(f, "-")
        det_forn.append(f"{f} (Nota: {nota_atrib})")

      tabela_itens_resumo.append({
          "Código": cod,
          "Categoria": categorias_dict.get(cod, "N/A"),
          "Descrição Oficial": descricoes_oficiais.get(cod, "N/A"),
          "Fornecedores e Escores": "; ".join(det_forn),
          "Qtd. Opções": qtd_forn,
      })
    st.dataframe(pd.DataFrame(tabela_itens_resumo), use_container_width=True)
  else:
    st.warning("Nenhum componente selecionado.")

  if st.button("🚀 Otimizar e Salvar Prescrição", type="primary"):
    nome_paciente_final = nome_paciente_input.strip()

    if not nome_paciente_final:
      st.error(
          "O campo 'Nome do Paciente / Responsável' não pode ficar em branco."
      )
      st.stop()

    if not itens_selecionados_ids:
      st.error("Selecione ao menos um componente antes de otimizar.")
      st.stop()

    # Validação mandatória: exatamente 1 chassi
    chassis_sel = [
        cod
        for cod in itens_selecionados_ids
        if categorias_dict.get(cod) == "Chassi"
    ]
    if len(chassis_sel) == 0:
      st.error(
          "❌ É obrigatório escolher pelo menos 1 chassi para compor a cadeira"
          " de rodas."
      )
      st.stop()
    elif len(chassis_sel) > 1:
      st.error(
          f"❌ Foram selecionados {len(chassis_sel)} chassis"
          f" ({', '.join(chassis_sel)}). É permitido escolher apenas 1 chassi."
      )
      st.stop()

    if existe_paciente_na_base(nome_paciente_final):
      st.error(
          f"O identificador '{nome_paciente_final}' já existe em"
          f" '{ARQUIVO_PRESC_SALVAS}'. Por favor, utilize um número sequencial"
          " diferente."
      )
      st.stop()

    if erro_notas_duplicadas:
      st.error(
          "❌ Existem itens com notas repetidas entre os fornecedores:"
          f" {', '.join(componentes_com_erro)}. Ajuste os escores para que"
          " sejam exclusivos (1, 2 e 3) antes de otimizar."
      )
      st.stop()

    with st.spinner("Executando PLIM e Força Bruta com as notas atribuídas..."):
      status_plim, custo_plim, qual_plim, fo_plim, df_det_plim = resolver_plim(
          itens_selecionados_ids,
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
          itens_selecionados_ids,
          LAMBDA,
          LIMITE_ORCAMENTO,
          mapa_qualidade_coletado,
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
          mapa_qualidade_item=mapa_qualidade_coletado,
      )

    st.success(
        f"Prescrição {id_prescricao_input} ({nome_paciente_final}) otimizada e"
        f" salva com sucesso em {ARQUIVO_PRESC_SALVAS}."
    )

    st.header("📊 Resultado Consolidado: Solver (PLIM) vs. Força Bruta (FB)")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Status da Solução", f"{status_plim} (PLIM)", f"{status_fb} (FB)"
    )
    c2.metric(
        "Custo Total",
        formatar_moeda(custo_plim),
        f"FB: {formatar_moeda(custo_fb)}",
    )
    c3.metric(
        "Qualidade Total", f"{qual_plim:.1f} pts", f"FB: {qual_fb:.1f} pts"
    )
    fo_plim_str = f"{fo_plim:.4f}" if fo_plim is not None else "N/A"
    fo_fb_str = f"{fo_fb:.4f}" if fo_fb is not None else "N/A"
    c4.metric("Valor Função Objetivo", fo_plim_str, f"FB: {fo_fb_str}")

    st.info(
        "🔍 **Espaço de Busca Exaustivo:**"
        f" `{formatar_inteiro(total_comb_fb)}` combinações avaliadas em"
        f" `{tempo_fb:.4f}` segundos.\n\n**Racional Multiplicativo:**"
        f" `{racional_espaco}`"
    )

    diff_fo = (
        abs(fo_plim - fo_fb)
        if (fo_plim is not None and fo_fb is not None)
        else 0.0
    )
    if diff_fo < 1e-4 and status_plim == status_fb:
      st.success(
          "Ótimo Global Comprovado: O solver PLIM convergiu exatamente para a"
          " mesma solução ótima obtida pela busca exaustiva."
      )
    else:
      st.warning(
          "Atenção: Detectada divergência matemática entre os métodos (ΔFO ="
          f" {diff_fo:.6f})."
      )

    st.subheader("🔍 Comparativo de Escolha por Componente (Lado a Lado)")
    df_comp = pd.merge(
        df_det_plim, df_det_fb, on="Componente", suffixes=(" (PLIM)", " (FB)")
    )
    st.dataframe(
        df_comp.style.format({
            "Valor do Item (PLIM)": formatar_moeda,
            "Valor do Item (FB)": formatar_moeda,
            "Pontos Qualidade (PLIM)": "{:.0f}",
            "Pontos Qualidade (FB)": "{:.0f}",
        }),
        use_container_width=True,
    )

# ----------------------------------------------------
# ABA 2: HISTÓRICO DE PRESCRIÇÕES SALVAS
# ----------------------------------------------------
with tab_historico:
  st.header("📂 Gerenciamento de Prescrições (Visualizar / Alterar / Excluir)")
  historico = carregar_prescricoes_salvas()

  if not historico:
    st.info("Nenhuma prescrição manual foi salva até o momento.")
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
            "nome_paciente": "Paciente / Responsável",
            "total_itens": "Qtd. Itens",
            "status_otimizacao": "Status",
            "custo_total": "Custo Total",
            "qualidade_total": "Qualidade",
            "valor_fo": "Valor FO",
            "lambda": "λ",
            "limite_orcamento": "Orçamento Máx.",
        }
    )

    st.dataframe(
        df_hist_vis.style.format({
            "Custo Total": formatar_moeda,
            "Orçamento Máx.": formatar_moeda,
            "Qualidade": "{:.1f} pts",
            "Valor FO": lambda x: f"{x:.4f}" if pd.notna(x) else "N/A",
            "λ": "{:.2f}",
        }),
        use_container_width=True,
    )

    json_bytes = json.dumps(historico, ensure_ascii=False, indent=2).encode(
        "utf-8"
    )
    st.download_button(
        label="📥 Baixar Base Completa de Prescrições (.json)",
        data=json_bytes,
        file_name=ARQUIVO_PRESC_SALVAS,
        mime="application/json",
    )

    st.divider()
    st.subheader("🛠️ Detalhes e Gerenciamento da Prescrição")

    opcoes_presc = [
        f"{p['id_prescricao']} | {p['nome_paciente']} ({p['data_hora']})"
        for p in historico
    ]
    escolha = st.selectbox(
        "Selecione a prescrição que deseja gerenciar:", opcoes_presc
    )

    if escolha:
      id_selecionado = escolha.split(" | ")[0]
      presc_detalhe = next(
          p for p in historico if p["id_prescricao"] == id_selecionado
      )

      mapa_qualidade_salvo = presc_detalhe.get("mapa_qualidade_item", {})

      c_info1, c_info2 = st.columns([3, 1])
      with c_info1:
        st.markdown(
            f"**ID:** `{presc_detalhe['id_prescricao']}` | **Paciente:**"
            f" `{presc_detalhe['nome_paciente']}`"
        )
        st.markdown(
            f"**Data de Criação:** {presc_detalhe['data_hora']} | **Modo de"
            f" Criação:** {presc_detalhe.get('modo_entrada', 'N/A')}"
        )
        st.markdown(
            f"**Custo Total:** `{formatar_moeda(presc_detalhe['custo_total'])}`"
            f" | **Qualidade:** `{presc_detalhe['qualidade_total']:.1f} pts` |"
            f" **Status:** `{presc_detalhe['status_otimizacao']}`"
        )

      with c_info2:
        if st.button(
            "🗑️ Excluir Prescrição",
            key=f"btn_del_{id_selecionado}",
            type="secondary",
        ):
          excluir_prescricao_salva(id_selecionado)
          st.warning(f"Prescrição {id_selecionado} excluída com sucesso.")
          st.rerun()

      if "detalhes_plim" in presc_detalhe and "detalhes_fb" in presc_detalhe:
        df_det_plim_hist = pd.DataFrame(presc_detalhe["detalhes_plim"])
        df_det_fb_hist = pd.DataFrame(presc_detalhe["detalhes_fb"])
      else:
        lam = float(presc_detalhe.get("lambda", 0.2))
        orc = float(presc_detalhe.get("limite_orcamento", 10000.0))
        _, _, _, _, df_det_plim_hist = resolver_plim(
            presc_detalhe["itens_prescritos"], lam, orc, mapa_qualidade_salvo
        )
        _, _, _, _, df_det_fb_hist, _, _, _ = resolver_forca_bruta(
            presc_detalhe["itens_prescritos"], lam, orc, mapa_qualidade_salvo
        )

      st.markdown("### 🔍 Comparativo de Escolha por Componente (Lado a Lado)")
      if not df_det_plim_hist.empty and not df_det_fb_hist.empty:
        df_comp_hist = pd.merge(
            df_det_plim_hist,
            df_det_fb_hist,
            on="Componente",
            suffixes=(" (PLIM)", " (FB)"),
        )
        st.dataframe(
            df_comp_hist.style.format({
                "Valor do Item (PLIM)": formatar_moeda,
                "Valor do Item (FB)": formatar_moeda,
                "Pontos Qualidade (PLIM)": "{:.0f}",
                "Pontos Qualidade (FB)": "{:.0f}",
            }),
            use_container_width=True,
        )
      else:
        st.warning(
            "Não há dados de detalhamento por componente para esta prescrição."
        )

      with st.expander("✏️ Editar e Reotimizar esta Prescrição"):
        st.markdown(
            f"Você está editando a prescrição **{id_selecionado}**."
        )

        col_ed1, col_ed2 = st.columns(2)
        with col_ed1:
          novo_nome = st.text_input(
              "Identificador do Paciente:",
              value=presc_detalhe["nome_paciente"],
              key=f"ed_nome_{id_selecionado}",
          )
          novo_lambda = st.slider(
              "Fator de Priorização (λ):",
              0.0,
              1.0,
              float(presc_detalhe.get("lambda", 0.2)),
              0.1,
              key=f"ed_lam_{id_selecionado}",
              help="Equilíbrio entre foco orçamentário e prioridade técnica.",
          )
        with col_ed2:
          novo_orcamento = st.number_input(
              "Limite Orçamentário (R$):",
              min_value=500.0,
              value=float(presc_detalhe.get("limite_orcamento", 10000.0)),
              step=500.0,
              key=f"ed_orc_{id_selecionado}",
          )

        todos_itens_cat = list(catmat_dict.keys())
        itens_atuais_validos = [
            i for i in presc_detalhe["itens_prescritos"] if i in catmat_dict
        ]

        novos_itens_escolhidos = st.multiselect(
            "Componentes da Prescrição (adicione ou remova itens):",
            options=todos_itens_cat,
            default=itens_atuais_validos,
            format_func=formatar_opcao_catalogo,
            key=f"ed_itens_{id_selecionado}",
            help=(
                "Pesquise por código CATMAT, categoria técnica ou termos da"
                " descrição oficial."
            ),
        )

        # Bloco de edição das notas técnicas
        st.markdown("#### Ajuste dos Escores Técnicos dos Componentes:")
        mapa_edicao_qualidade = {}
        erro_edicao_notas = False

        for k_ed in novos_itens_escolhidos:
          forns_ed = list(catmat_dict.get(k_ed, {}).keys())
          st.caption(f"**Item {k_ed}:** {descricoes_oficiais.get(k_ed, '')[:60]}...")
          cols_ed = st.columns(len(forns_ed))
          notas_ed_k = {}

          for idx_fe, fe in enumerate(forns_ed):
            val_salvo = mapa_qualidade_salvo.get(k_ed, {}).get(
                fe, padrao_inicial_notas.get(fe, max(1, 3 - idx_fe))
            )
            with cols_ed[idx_fe]:
              n_ed = st.selectbox(
                  f"{fe} ({k_ed})",
                  options=[3, 2, 1],
                  index=[3, 2, 1].index(val_salvo) if val_salvo in [3, 2, 1] else 0,
                  key=f"ed_q_{id_selecionado}_{k_ed}_{fe}",
              )
              notas_ed_k[fe] = n_ed

          if len(notas_ed_k.values()) != len(set(notas_ed_k.values())):
            st.error(f"Escores repetidos para o item {k_ed} na edição!")
            erro_edicao_notas = True

          mapa_edicao_qualidade[k_ed] = notas_ed_k

        if st.button(
            "💾 Salvar Alterações e Reotimizar",
            key=f"btn_save_edit_{id_selecionado}",
            type="primary",
        ):
          if not novo_nome.strip():
            st.error("O identificador do paciente não pode ficar em branco.")
          elif existe_paciente_na_base(novo_nome, id_ignorar=id_selecionado):
            st.error(
                f"O identificador '{novo_nome}' já pertence a outra prescrição"
                " cadastrada."
            )
          elif not novos_itens_escolhidos:
            st.error("A prescrição deve conter ao menos um componente.")
          else:
            chassis_edicao = [
                cod
                for cod in novos_itens_escolhidos
                if categorias_dict.get(cod) == "Chassi"
            ]
            if len(chassis_edicao) == 0:
              st.error(
                  "❌ É obrigatório manter exatamente 1 chassi na prescrição."
              )
            elif len(chassis_edicao) > 1:
              st.error(
                  f"❌ Foram selecionados {len(chassis_edicao)} chassis. É"
                  " permitido apenas 1 chassi."
              )
            elif erro_edicao_notas:
              st.error("❌ Corrija as notas duplicadas antes de reotimizar.")
            else:
              with st.spinner("Reotimizando a prescrição alterada..."):
                st_plim, c_plim, q_plim, f_plim, df_d_plim = resolver_plim(
                    novos_itens_escolhidos,
                    novo_lambda,
                    novo_orcamento,
                    mapa_edicao_qualidade,
                )
                st_fb, c_fb, q_fb, f_fb, df_d_fb, _, _, _ = (
                    resolver_forca_bruta(
                        novos_itens_escolhidos,
                        novo_lambda,
                        novo_orcamento,
                        mapa_edicao_qualidade,
                    )
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
                    mapa_qualidade_item=mapa_edicao_qualidade,
                )

              st.success(
                  f"Prescrição {id_selecionado} atualizada e reotimizada com"
                  " sucesso."
              )
              st.rerun()