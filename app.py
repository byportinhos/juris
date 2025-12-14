import streamlit as st
import mysql.connector
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from docx import Document
from io import BytesIO
from PIL import Image
import re
import requests
import json

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Advogado AI - Dados Reais", layout="wide", page_icon="⚖️")

# 1. Configurar Google Gemini
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash') 
except Exception as e:
    st.error("Erro na API Key do Google. Configure os Secrets.")
    st.stop()

# 2. Configurar Conexão Hostgator (MySQL)
def get_db_connection():
    return mysql.connector.connect(
        host=st.secrets["database"]["DB_HOST"],
        user=st.secrets["database"]["DB_USER"],
        password=st.secrets["database"]["DB_PASS"],
        database=st.secrets["database"]["DB_NAME"]
    )

# 3. Configuração DATAJUD (Mapeamento de Tribunais)
URLS_DATAJUD = {
    "TJRJ": "https://api-publica.datajud.cnj.jus.br/api_publica_tjrj/_search",
    "TJSP": "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search",
    "TJMG": "https://api-publica.datajud.cnj.jus.br/api_publica_tjmg/_search",
    "TJRS": "https://api-publica.datajud.cnj.jus.br/api_publica_tjrs/_search",
    "TJBA": "https://api-publica.datajud.cnj.jus.br/api_publica_tjba/_search"
}

# --- FUNÇÕES DE BUSCA REAL (DATAJUD) ---

def consultar_api_datajud(tribunal, nome_juiz, termo_busca="Dano Moral"):
    """
    Busca no DataJud procurando as palavras do nome do juiz DENTRO das movimentações.
    Usa lógica AND para todas as palavras.
    """
    url = URLS_DATAJUD.get(tribunal)
    if not url:
        return "Tribunal não mapeado na API Pública."

    # Limpeza de caracteres especiais
    nome_limpo = re.sub(r'[^a-zA-Z0-9\s]', '', nome_juiz)
    tema_limpo = re.sub(r'[^a-zA-Z0-9\s]', '', termo_busca)
    
    # Montamos uma query que exige TODAS as palavras do nome + o tema
    # Ex: se digitar "João Silva", a query procura: (+João +Silva) E (+Dano +Moral)
    query_final = f"({nome_limpo}) AND ({tema_limpo})"
    
    payload = {
        "size": 20,
        "query": {
            "simple_query_string": {
                "query": query_final,
                # Procura no campo genérico (textão) e nas movimentações onde o juiz assina
                "fields": ["movimentos.complementos.descricao", "movimentos.nome", "orgaoJulgador.nome"],
                "default_operator": "and" # O PULO DO GATO: Obriga ter todas as palavras
            }
        },
        "sort": [{"dataAjuizamento": "desc"}]
    }

    headers = {"Content-Type": "application/json"}
    if "DATAJUD_API_KEY" in st.secrets:
        headers["Authorization"] = f"ApiKey {st.secrets['DATAJUD_API_KEY']}"

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=25)
        
        if response.status_code == 200:
            dados = response.json()
            hits = dados.get("hits", {}).get("hits", [])
            
            if not hits:
                return [] # Retorna lista vazia se não achar nada (para tratar na tela)

            lista_processos = []
            for hit in hits:
                source = hit.get("_source", {})
                
                # Formatação dos dados
                assuntos = ", ".join([a.get("nome") for a in source.get("assuntos", [])])
                orgao = source.get("orgaoJulgador", {}).get("nome", "Vara não informada")
                
                # Tenta achar o nome do juiz nos movimentos para exibir na tabela
                # (Isso é apenas visual, a busca já filtrou)
                movs = source.get("movimentos", [])
                ultimo_mov = movs[0].get("nome") if movs else "Sem movimento"
                
                proc = {
                    "numero": source.get("numeroProcesso"),
                    "classe": source.get("classe", {}).get("nome"),
                    "assuntos": assuntos,
                    "data": source.get("dataAjuizamento"),
                    "orgao": orgao,
                    "ultimo_movimento": ultimo_mov
                }
                lista_processos.append(proc)
            
            return lista_processos
        else:
            return f"Erro API CNJ ({response.status_code}): {response.text}"
            
    except Exception as e:
        return f"Erro de conexão: {e}"
# --- AGENTES DE INTELIGÊNCIA ---

def agente_peticao_inicial_com_calculo(relato_texto, imagens_upload, tribunal):
    lista_conteudo = []
    prompt_sistema = f"""
    Você é um Advogado Sênior. 
    1. Calcule o valor da causa (Quantum Indenizatório) com base no teto do {tribunal}.
    2. Redija a Petição Inicial.
    3. No final, coloque: [[VALOR_CALCULADO: R$ 0.000,00]]
    """
    lista_conteudo.append(prompt_sistema)
    lista_conteudo.append(f"Fatos: {relato_texto}")
    
    if imagens_upload:
        for arq in imagens_upload:
            try:
                img = Image.open(arq)
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    img = img.convert('RGB')
                img.thumbnail((1024, 1024))
                lista_conteudo.append(img)
            except: pass
            
    try:
        response = model.generate_content(lista_conteudo, request_options={"timeout": 600})
        return response.text
    except Exception as e: return str(e)

def agente_jurimetria_com_dados_reais(nome_juiz, tribunal, fatos_cliente, processos_reais):
    """
    Analisa os processos REAIS retornados pela API e encontra o melhor argumento.
    """
    prompt = f"""
    Atue como Especialista em Jurimetria.
    
    DADOS DO CASO:
    - Juiz Alvo: {nome_juiz} ({tribunal})
    - Nosso Caso: {fatos_cliente}
    
    BASE DE DADOS REAL (DATAJUD/CNJ):
    Abaixo segue uma lista de processos REAIS encontrados desse juiz/tribunal via API:
    {json.dumps(processos_reais, indent=2, ensure_ascii=False)}
    
    TAREFA:
    1. Analise a lista acima. Escolha UM processo real para usar como "Processo Paradigma".
    2. Se a lista estiver vazia ou não tiver o juiz exato, use seu conhecimento interno, MAS AVISE que não encontrou na API.
    3. Gere a análise estratégica.
    
    SAÍDA (Markdown):
    ### 🏆 O Processo Paradigma (Real)
    *   **Número:** [Use o número exato do JSON acima]
    *   **Data:** [Data do JSON]
    *   **Classe/Assunto:** [Do JSON]
    *   **Análise:** Por que este caso serve de exemplo para nós? (Se for assunto similar).
    
    ### 💰 Expectativa de Valor
    Baseado no padrão desse tribunal e nesses casos listados, qual o teto realista?
    
    ### ⚠️ Risco Detectado
    Algum desses processos foi improcedente?
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro Jurimetria IA: {e}"

def agente_comunicacao(fase, nome_cliente, extra=None):
    prompt = f"Crie msg WhatsApp para {nome_cliente}. Fase: {fase}. {extra if extra else ''}."
    response = model.generate_content(prompt)
    return response.text

# --- INTERFACE ---
st.title("⚖️ Advogado AI - Sistema Estrategista (DataJud Real)")

menu = st.sidebar.radio("Navegação", ["1. Novo Caso", "2. Carteira (CRM)", "3. Jurimetria Real"])

# --- ABA 1: NOVO CASO ---
if menu == "1. Novo Caso":
    st.header("📂 Cadastro Inteligente")
    with st.form("form_inicial"):
        col1, col2 = st.columns(2)
        cliente = col1.text_input("Cliente")
        telefone = col1.text_input("WhatsApp")
        tribunal = col2.selectbox("Tribunal", ["TJRJ", "TJSP", "TJMG", "TJRS", "TJBA"])
        relato = st.text_area("Fatos", height=150)
        provas = st.file_uploader("Provas", type=["png","jpg"], accept_multiple_files=True)
        btn_gerar = st.form_submit_button("🤖 Gerar Inicial")

    if btn_gerar and cliente and relato:
        with st.spinner(f"Calculando valor e gerando peça..."):
            texto = agente_peticao_inicial_com_calculo(relato, provas, tribunal)
            
            valor = "Sob Análise"
            match = re.search(r"\[\[VALOR_CALCULADO:\s*(.*?)\]\]", texto)
            if match: valor = match.group(1)
            
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                hist = f"RELATO_FATOS: {relato} || VALOR_IA: {valor} || DATA: {datetime.now()}"
                sql = "INSERT INTO processos (cliente_nome, cliente_telefone, tribunal, status, historico) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(sql, (cliente, telefone, tribunal, "Inicial Pronta", hist))
                conn.commit()
                conn.close()
                st.toast(f"Salvo! Valor: {valor}", icon="💰")
            except Exception as e: st.error(str(e))
            
            st.markdown(f"### 💰 Valor Sugerido: **{valor}**")
            st.download_button("Baixar Inicial", data=texto, file_name=f"{cliente}.txt")

# --- ABA 2: CRM ---
elif menu == "2. Carteira (CRM)":
    st.header("🗂️ Gestão")
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM processos ORDER BY id DESC", conn)
        conn.close()
        if len(df) > 0:
            sel = st.selectbox("Cliente", df["cliente_nome"])
            dados = df[df["cliente_nome"] == sel].iloc[0]
            st.write(f"Tribunal: {dados['tribunal']} | Status: {dados['status']}")
            
            tab1, tab2 = st.tabs(["Histórico", "Ações"])
            with tab1: st.write(dados['historico'])
            with tab2: 
                dt = st.date_input("Data Audiência")
                if st.button("Gerar Aviso"): 
                    st.code(agente_comunicacao("Audiência", dados['cliente_nome'], str(dt)))
    except: pass

# --- ABA 3: JURIMETRIA REAL (DATAJUD) ---
elif menu == "3. Jurimetria Real":
    st.header("🏆 Busca de Precedentes Reais (DataJud)")
    st.info("O sistema vai conectar na API do CNJ para buscar números de processos reais.")
    
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT cliente_nome, historico, tribunal FROM processos", conn)
        conn.close()
        
        if len(df) > 0:
            col1, col2 = st.columns(2)
            cli = col1.selectbox("Cliente", df["cliente_nome"])
            
            # Recupera dados
            dado = df[df["cliente_nome"] == cli].iloc[0]
            tribunal_auto = dado["tribunal"]
            if "RELATO_FATOS:" in dado["historico"]:
                fatos = dado["historico"].split("RELATO_FATOS:")[1].split("||")[0]
            else: fatos = dado["historico"]
            
            st.caption(f"Caso: {fatos[:100]}...")
            
            juiz = col2.text_input("Nome do Juiz(a):")
            tema_busca = col2.text_input("Palavra-Chave da Busca (Ex: Dano Moral)", value="Dano Moral")
            
            if st.button("🔍 Investigar no CNJ"):
                if juiz:
                    with st.status("Investigando...", expanded=True) as status:
                        # 1. Busca na API DataJud
                        status.write("Conectando ao DataJud/CNJ...")
                        processos_encontrados = consultar_api_datajud(tribunal_auto, juiz, tema_busca)
                        
                        if isinstance(processos_encontrados, list) and len(processos_encontrados) > 0:
                            status.write(f"✅ Encontrados {len(processos_encontrados)} processos reais!")
                            st.dataframe(pd.DataFrame(processos_encontrados)) # Mostra tabela bruta
                            
                            # 2. Analisa com Gemini
                            status.write("Gemini está lendo os processos...")
                            analise = agente_jurimetria_com_dados_reais(
                                juiz, tribunal_auto, fatos, processos_encontrados
                            )
                            st.markdown("---")
                            st.markdown(analise)
                            
                        elif isinstance(processos_encontrados, list) and len(processos_encontrados) == 0:
                            st.warning("A API do CNJ retornou 0 processos com esse nome de juiz/termo exato.")
                            st.info("Dica: Tente apenas o sobrenome do juiz ou mude a palavra-chave.")
                        else:
                            st.error(f"Erro na API: {processos_encontrados}")
                            
                        status.update(label="Concluído!", state="complete", expanded=False)
                else:
                    st.warning("Digite o Juiz.")
        else:
            st.warning("Sem clientes.")
    except Exception as e: st.error(str(e))



