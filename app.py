import streamlit as st
import mysql.connector
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from docx import Document
from io import BytesIO
from PIL import Image
import re
# NOVA BIBLIOTECA DE BUSCA (ESTÁVEL)
from duckduckgo_search import DDGS

# --- CONFIGURAÇÕES GERAIS ---
st.set_page_config(page_title="Advogado AI - Multimodal", layout="wide", page_icon="⚖️")

# 1. Configurar Gemini
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash') 
except:
    st.error("ERRO: Configure a GOOGLE_API_KEY nos Secrets do Streamlit.")
    st.stop()

# 2. Conexão Banco de Dados (Hostgator)
def get_db_connection():
    return mysql.connector.connect(
        host=st.secrets["database"]["DB_HOST"],
        user=st.secrets["database"]["DB_USER"],
        password=st.secrets["database"]["DB_PASS"],
        database=st.secrets["database"]["DB_NAME"]
    )

# --- FUNÇÕES DE BUSCA (JURIMETRIA VIA DUCKDUCKGO) ---
def buscar_jurisprudencia_ddg(nome_juiz, tema):
    """
    Usa DuckDuckGo para evitar bloqueio 429 do Google.
    """
    resultados = []
    # Query focada: Tenta achar Jusbrasil, Escavador ou sites de tribunais
    query = f'{nome_juiz} "{tema}" sentença site:jusbrasil.com.br OR site:escavador.com'
    
    try:
        # Usa o contexto do DDGS para buscar
        with DDGS() as ddgs:
            # Busca 10 resultados
            ddg_results = list(ddgs.text(query, max_results=10))
            
            for item in ddg_results:
                resultados.append({
                    "titulo": item['title'],
                    "link": item['href'],
                    "resumo": item['body']
                })
        return resultados
    except Exception as e:
        st.error(f"Erro na busca: {e}")
        return []

# --- AGENTES DE INTELIGÊNCIA ---

def agente_peticao_multimodal(relato, imagens, tribunal):
    """
    Gera petição lendo TEXTO + IMAGENS (Prints).
    """
    conteudo = []
    
    prompt = f"""
    Você é um Advogado Sênior Especialista.
    1. Analise o relato e as IMAGENS anexadas (se houver).
    2. Identifique dados nas imagens (datas, valores, ofensas) e cite em "Dos Fatos".
    3. Calcule o valor da causa baseado no teto do {tribunal}.
    4. Redija a Inicial completa.
    5. No fim, coloque [[VALOR_CALCULADO: R$ ...]]
    """
    conteudo.append(prompt)
    conteudo.append(f"RELATO CLIENTE: {relato}")
    
    # Processamento de Imagens
    if imagens:
        conteudo.append("PROVAS VISUAIS (ANEXOS):")
        for arq in imagens:
            try:
                img = Image.open(arq)
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    img = img.convert('RGB')
                img.thumbnail((1024, 1024))
                conteudo.append(img)
            except Exception as e:
                print(f"Erro imagem: {e}")
                
    try:
        response = model.generate_content(conteudo, request_options={"timeout": 600})
        return response.text
    except Exception as e:
        return f"Erro na IA: {e}"

def agente_analise_jurimetria(lista_resultados, nome_juiz, caso_cliente):
    """
    Lê os resultados da busca e gera estratégia.
    """
    texto_links = ""
    for r in lista_resultados[:6]: 
        texto_links += f"- Título: {r['titulo']}\n  Resumo: {r['resumo']}\n  Link: {r['link']}\n\n"
        
    prompt = f"""
    ATUE COMO DATA SCIENTIST JURÍDICO.
    
    MEU CASO: {caso_cliente}
    JUIZ ALVO: {nome_juiz}
    
    ENCONTREI ESSES LINKS NA WEB (Jusbrasil/Escavador):
    {texto_links}
    
    ANÁLISE NECESSÁRIA:
    1. Baseado nos títulos/resumos, esse juiz costuma julgar PROCEDENTE esse tipo de tema?
    2. Tente encontrar um NÚMERO DE PROCESSO no texto dos resumos para usarmos de paradigma.
    3. Qual a "temperatura" dele? (Rigoroso ou Pró-Consumidor?)
    
    SAÍDA (Markdown):
    ### 📊 Veredito Preliminar
    (Sua análise sobre a chance de vitória)
    
    ### 🏆 Caso Semelhante Encontrado
    (Se achou algum processo citado nos resumos, mostre aqui).
    
    ### 🔗 Fontes para Consulta
    (Liste os links para eu clicar).
    """
    return model.generate_content(prompt).text

def agente_comunicacao(fase, nome):
    return model.generate_content(f"Msg WhatsApp curta para {nome} sobre fase {fase}.").text

# --- INTERFACE ---
st.title("⚖️ Advogado AI - Sistema Completo")

menu = st.sidebar.radio("Menu", ["1. Novo Caso (Com Prints)", "2. Carteira CRM", "3. Jurimetria (Web Search)"])

# --- ABA 1: NOVO CASO ---
if menu == "1. Novo Caso (Com Prints)":
    st.header("📂 Cadastro & Petição Multimodal")
    
    with st.form("form_novo"):
        c1, c2 = st.columns(2)
        cli = c1.text_input("Nome Cliente")
        tel = c1.text_input("WhatsApp")
        trib = c2.selectbox("Tribunal", ["TJRJ", "TJSP", "TJMG", "Outros"])
        
        relato = st.text_area("Fatos do Caso", height=150)
        arquivos = st.file_uploader("Anexar Provas (Prints/Fotos)", type=["png","jpg","jpeg"], accept_multiple_files=True)
        
        btn_gerar = st.form_submit_button("🤖 Analisar Provas e Gerar Inicial")

    if btn_gerar and cli and relato:
        with st.spinner("Lendo imagens e redigindo..."):
            peticao = agente_peticao_multimodal(relato, arquivos, trib)
            valor = "A Calcular"
            match = re.search(r"\[\[VALOR_CALCULADO:\s*(.*?)\]\]", peticao)
            if match: valor = match.group(1)
            
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                hist = f"FATOS: {relato} || VALOR: {valor} || DATA: {datetime.now()}"
                if arquivos: hist += " || [COM IMAGENS]"
                sql = "INSERT INTO processos (cliente_nome, cliente_telefone, tribunal, status, historico) VALUES (%s,%s,%s,%s,%s)"
                cur.execute(sql, (cli, tel, trib, "Inicial Pronta", hist))
                conn.commit()
                conn.close()
                st.toast(f"Salvo! Valor: {valor}")
            except Exception as e: st.error(str(e))
            
            st.markdown(f"### 💰 Valor Sugerido: {valor}")
            st.download_button("Baixar Inicial (.docx)", peticao, f"{cli}.txt")

# --- ABA 2: CRM ---
elif menu == "2. Carteira CRM":
    st.header("🗂️ Gestão")
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM processos ORDER BY id DESC", conn)
        conn.close()
        if not df.empty:
            sel = st.selectbox("Cliente", df["cliente_nome"])
            dado = df[df["cliente_nome"] == sel].iloc[0]
            st.write(f"Tribunal: {dado['tribunal']} | Status: {dado['status']}")
            t1, t2 = st.tabs(["Histórico", "WhatsApp"])
            with t1: st.write(dado['historico'])
            with t2:
                dt = st.date_input("Data Audiência")
                if st.button("Criar Texto Zap"):
                    st.code(agente_comunicacao("Audiência", dado['cliente_nome']))
    except: pass

# --- ABA 3: JURIMETRIA (DUCKDUCKGO) ---
elif menu == "3. Jurimetria (Web Search)":
    st.header("🌎 Investigação Web (Sem Bloqueios)")
    st.info("Buscando no Jusbrasil/Escavador via DuckDuckGo.")
    
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT cliente_nome, historico, tribunal FROM processos", conn)
        conn.close()
        
        if not df.empty:
            c1, c2 = st.columns(2)
            sel_cli = c1.selectbox("Cliente", df["cliente_nome"])
            dado = df[df["cliente_nome"] == sel_cli].iloc[0]
            
            fatos_raw = dado["historico"]
            if "FATOS:" in fatos_raw:
                fatos_limpos = fatos_raw.split("FATOS:")[1].split("||")[0]
            else: fatos_limpos = fatos_raw
            
            st.caption(f"**Caso:** {fatos_limpos[:100]}...")
            
            juiz = c2.text_input("Nome do Juiz:")
            tema = c2.text_input("Tema:", value="Dano Moral")
            
            if st.button("🔍 Pesquisar"):
                if juiz:
                    with st.status("Pesquisando...", expanded=True) as s:
                        # Busca via DuckDuckGo
                        s.write("Varrendo a web...")
                        resultados = buscar_jurisprudencia_ddg(juiz, tema)
                        
                        if resultados:
                            s.write(f"Encontrados {len(resultados)} links!")
                            # Mostra tabela simples
                            df_res = pd.DataFrame(resultados)
                            st.dataframe(df_res[["titulo", "link"]])
                            
                            s.write("Gemini está analisando...")
                            analise = agente_analise_jurimetria(resultados, juiz, fatos_limpos)
                            
                            st.markdown("---")
                            st.markdown(analise)
                        else:
                            st.warning("Nenhum resultado encontrado. Tente simplificar o nome do juiz.")
                            
                        s.update(label="Pronto!", state="complete")
                else:
                    st.warning("Digite o Juiz")
        else:
            st.warning("Cadastre clientes primeiro.")
    except Exception as e: st.error(str(e))
