import streamlit as st
import mysql.connector
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from docx import Document
from io import BytesIO
from PIL import Image
import re
from duckduckgo_search import DDGS

# --- CONFIGURAÇÕES GERAIS ---
st.set_page_config(page_title="Advogado AI - Final", layout="wide", page_icon="⚖️")

# 1. Configurar Gemini
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash') 
except:
    st.error("ERRO: Configure a GOOGLE_API_KEY nos Secrets do Streamlit.")
    st.stop()

# 2. Conexão Banco de Dados
def get_db_connection():
    return mysql.connector.connect(
        host=st.secrets["database"]["DB_HOST"],
        user=st.secrets["database"]["DB_USER"],
        password=st.secrets["database"]["DB_PASS"],
        database=st.secrets["database"]["DB_NAME"]
    )

# --- FUNÇÃO DE BUSCA ROBUSTA (DUCKDUCKGO BRASIL) ---
def buscar_jurisprudencia_ddg(nome_juiz, tema):
    """
    Busca forçada na região Brasil (br-pt) para encontrar Jusbrasil/Tribunais.
    """
    resultados = []
    
    # Query Simplificada: Funciona melhor que operadores complexos na API
    # Ex: "Juiz João da Silva Dano Moral sentença Jusbrasil"
    query = f'Juiz {nome_juiz} {tema} sentença Jusbrasil'
    
    try:
        with DDGS() as ddgs:
            # region='br-pt' é o segredo para achar coisas locais
            # timelimit='y' busca coisas do último ano (opcional, tirei para trazer tudo)
            ddg_results = ddgs.text(query, region='br-pt', max_results=10)
            
            for item in ddg_results:
                resultados.append({
                    "titulo": item.get('title', 'Sem título'),
                    "link": item.get('href', item.get('link', '#')),
                    "resumo": item.get('body', item.get('snippet', ''))
                })
        return resultados
    except Exception as e:
        st.error(f"Erro técnico na busca: {e}")
        return []

# --- AGENTES DE INTELIGÊNCIA ---

def agente_peticao_multimodal(relato, imagens, tribunal):
    conteudo = []
    prompt = f"""
    Você é um Advogado Sênior.
    1. Analise relato e IMAGENS (se houver).
    2. Identifique dados nas imagens (datas, valores) e cite em "Dos Fatos".
    3. Calcule o valor da causa baseado no teto do {tribunal}.
    4. Redija a Inicial.
    5. No fim, coloque [[VALOR_CALCULADO: R$ ...]]
    """
    conteudo.append(prompt)
    conteudo.append(f"RELATO: {relato}")
    
    if imagens:
        conteudo.append("PROVAS (ANEXOS):")
        for arq in imagens:
            try:
                img = Image.open(arq)
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    img = img.convert('RGB')
                img.thumbnail((1024, 1024))
                conteudo.append(img)
            except: pass
                
    try:
        response = model.generate_content(conteudo, request_options={"timeout": 600})
        return response.text
    except Exception as e: return f"Erro IA: {e}"

def agente_analise_jurimetria(lista_resultados, nome_juiz, caso_cliente):
    texto_links = ""
    for r in lista_resultados[:5]: 
        texto_links += f"- Título: {r['titulo']}\n  Resumo: {r['resumo']}\n  Link: {r['link']}\n\n"
        
    prompt = f"""
    ATUE COMO ESPECIALISTA EM JURIMETRIA.
    CASO: {caso_cliente}
    JUIZ: {nome_juiz}
    
    DADOS DA WEB (Jusbrasil/TJs):
    {texto_links}
    
    TAREFA:
    1. Baseado nesses resumos, o juiz costuma julgar PROCEDENTE?
    2. Tente extrair um NÚMERO DE PROCESSO citado nos resumos/títulos.
    3. Analise a tendência de valor.
    
    SAÍDA (Markdown):
    ### 📊 Veredito
    (Sua análise)
    
    ### 🏆 Precedente Encontrado
    (Se houver número de processo, cite aqui).
    
    ### 🔗 Fontes
    (Liste os links).
    """
    return model.generate_content(prompt).text

def agente_comunicacao(fase, nome):
    return model.generate_content(f"Msg WhatsApp curta para {nome} sobre fase {fase}.").text

# --- INTERFACE ---
st.title("⚖️ Advogado AI - Sistema Final")

menu = st.sidebar.radio("Menu", ["1. Novo Caso", "2. Carteira CRM", "3. Jurimetria Web"])

# ABA 1
if menu == "1. Novo Caso":
    st.header("📂 Cadastro")
    with st.form("form_novo"):
        c1, c2 = st.columns(2)
        cli = c1.text_input("Cliente")
        tel = c1.text_input("WhatsApp")
        trib = c2.selectbox("Tribunal", ["TJRJ", "TJSP", "TJMG", "Outros"])
        relato = st.text_area("Fatos")
        arquivos = st.file_uploader("Provas", type=["png","jpg","jpeg"], accept_multiple_files=True)
        btn_gerar = st.form_submit_button("Gerar Inicial")

    if btn_gerar and cli and relato:
        with st.spinner("Gerando..."):
            peticao = agente_peticao_multimodal(relato, arquivos, trib)
            valor = "A Calcular"
            match = re.search(r"\[\[VALOR_CALCULADO:\s*(.*?)\]\]", peticao)
            if match: valor = match.group(1)
            
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                hist = f"FATOS: {relato} || VALOR: {valor} || DATA: {datetime.now()}"
                if arquivos: hist += " || [COM IMAGENS]"
                cur.execute("INSERT INTO processos (cliente_nome, cliente_telefone, tribunal, status, historico) VALUES (%s,%s,%s,%s,%s)", 
                            (cli, tel, trib, "Inicial Pronta", hist))
                conn.commit()
                conn.close()
                st.toast(f"Salvo! Valor: {valor}")
            except Exception as e: st.error(str(e))
            
            st.markdown(f"### 💰 Valor: {valor}")
            st.download_button("Baixar", peticao, f"{cli}.txt")

# ABA 2
elif menu == "2. Carteira CRM":
    st.header("🗂️ CRM")
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM processos ORDER BY id DESC", conn)
        conn.close()
        if not df.empty:
            sel = st.selectbox("Cliente", df["cliente_nome"])
            dado = df[df["cliente_nome"] == sel].iloc[0]
            st.write(f"Tribunal: {dado['tribunal']}")
            st.write(dado['historico'])
            if st.button("Gerar Zap"):
                st.code(agente_comunicacao("Audiência", dado['cliente_nome']))
    except: pass

# ABA 3 (JURIMETRIA CORRIGIDA)
elif menu == "3. Jurimetria Web":
    st.header("🌎 Jurimetria (Busca Brasil)")
    
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT cliente_nome, historico FROM processos", conn)
        conn.close()
        
        if not df.empty:
            c1, c2 = st.columns(2)
            sel_cli = c1.selectbox("Cliente", df["cliente_nome"])
            dado = df[df["cliente_nome"] == sel_cli].iloc[0]
            
            fatos = dado["historico"]
            if "FATOS:" in fatos: fatos = fatos.split("FATOS:")[1].split("||")[0]
            
            st.caption(f"Caso: {fatos[:100]}...")
            
            juiz = c2.text_input("Nome do Juiz (Ex: João da Silva):")
            tema = c2.text_input("Tema (Ex: Dano Moral):", value="Dano Moral")
            
            if st.button("🔍 Pesquisar"):
                if juiz:
                    with st.status("Buscando...", expanded=True) as s:
                        # 1. Busca DDG Região Brasil
                        resultados = buscar_jurisprudencia_ddg(juiz, tema)
                        
                        if resultados:
                            s.write(f"✅ Encontrados {len(resultados)} resultados.")
                            st.dataframe(pd.DataFrame(resultados)[['titulo', 'link']])
                            
                            # 2. IA
                            s.write("Analisando...")
                            analise = agente_analise_jurimetria(resultados, juiz, fatos)
                            st.markdown("---")
                            st.markdown(analise)
                        else:
                            st.warning("A busca automática não retornou links diretos.")
                            # LINK DE PLANO B
                            link_manual = f"https://www.google.com/search?q=sentença+juiz+{juiz.replace(' ', '+')}+{tema.replace(' ', '+')}+jusbrasil"
                            st.markdown(f"👉 **[Clique aqui para abrir a pesquisa manual no Google]({link_manual})** e veja os resultados você mesmo.")
                            
                        s.update(label="Fim", state="complete")
                else:
                    st.warning("Digite o Juiz")
        else:
            st.warning("Sem clientes.")
    except Exception as e: st.error(str(e))
