import streamlit as st
import mysql.connector
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from docx import Document
from io import BytesIO
from PIL import Image
import re
# Biblioteca de busca do Google
from googlesearch import search 

# --- CONFIGURAÇÕES ---
st.set_page_config(page_title="Advogado AI - Web Search", layout="wide", page_icon="⚖️")

# 1. Configurar Gemini
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash') 
except:
    st.error("Configure a GOOGLE_API_KEY nos Secrets.")
    st.stop()

# 2. Conexão DB
def get_db_connection():
    return mysql.connector.connect(
        host=st.secrets["database"]["DB_HOST"],
        user=st.secrets["database"]["DB_USER"],
        password=st.secrets["database"]["DB_PASS"],
        database=st.secrets["database"]["DB_NAME"]
    )

# --- FUNÇÃO DE BUSCA GOOGLE (A SALVAÇÃO) ---
def buscar_jurisprudencia_google(nome_juiz, tema, tribunal):
    """
    Usa o Google para encontrar links do Jusbrasil/Tribunais que citem o juiz e o tema.
    """
    resultados = []
    # Query focada em achar sentenças ou acordãos
    query = f'site:jusbrasil.com.br OR site:escavador.com OR site:tjsp.jus.br "{nome_juiz}" "{tema}" sentença'
    
    try:
        # Busca 10 resultados
        search_results = search(query, num_results=10, advanced=True)
        
        for item in search_results:
            resultados.append({
                "titulo": item.title,
                "link": item.url,
                "resumo": item.description # O Google nos dá um resumo do que achou
            })
        return resultados
    except Exception as e:
        st.error(f"Erro na busca Google: {e}")
        return []

# --- AGENTES IA ---
def agente_analise_google(resultados_google, nome_juiz, meu_caso):
    """
    O Gemini lê os RESUMOS do Google e tenta extrair inteligência deles.
    """
    resultados_texto = ""
    for i, res in enumerate(resultados_google):
        resultados_texto += f"Result {i+1}: {res['titulo']} | Resumo: {res['resumo']} | Link: {res['link']}\n\n"

    prompt = f"""
    ATUE COMO ESPECIALISTA EM JURIMETRIA.
    
    MEU CASO: {meu_caso}
    JUIZ ALVO: {nome_juiz}
    
    DADOS ENCONTRADOS NA WEB (Google):
    {resultados_texto}
    
    TAREFA:
    1. Leia os resultados acima. Tente identificar algum PADRÃO ou um NÚMERO DE PROCESSO real citado nos títulos/resumos.
    2. Se achar um processo com tema similar, use-o como paradigma.
    
    SAÍDA (Markdown):
    ### 🕵️ Análise dos Resultados Web
    *   **Tendência Encontrada:** (O que os títulos do Jusbrasil sugerem sobre esse juiz? Ele condena ou absolve?)
    *   **Melhor Precedente Encontrado:** (Cite o Título/Link e se possível o número do processo se estiver visível).
    
    ### ⚖️ Comparativo
    *   **Probabilidade:** Baseado nesses links, qual a chance de êxito?
    *   **Valor Estimado:** O juiz parece fixar valores altos?
    
    ### 🔗 Fontes Reais
    (Liste os 3 links mais relevantes para o advogado clicar e ler a íntegra).
    """
    response = model.generate_content(prompt)
    return response.text

def agente_peticao(relato, tribunal):
    prompt = f"Escreva uma Petição Inicial completa para o {tribunal}. Fatos: {relato}. Calcule um valor alto de causa baseado no teto do tribunal. No final coloque [[VALOR: R$ ...]]."
    return model.generate_content(prompt).text

def agente_comunicacao(fase, nome):
    return model.generate_content(f"Msg WhatsApp curta para {nome} sobre fase {fase}.").text

# --- INTERFACE ---
st.title("⚖️ Advogado AI - Jurimetria via Web")

menu = st.sidebar.radio("Menu", ["1. Novo Caso", "2. Carteira CRM", "3. Jurimetria (Google Search)"])

# ABA 1 e 2 (Resumidas para focar na 3)
if menu == "1. Novo Caso":
    st.header("Novo Caso")
    with st.form("f1"):
        cli = st.text_input("Cliente")
        trib = st.selectbox("Tribunal", ["TJSP", "TJRJ", "TJMG", "Outros"])
        fat = st.text_area("Fatos")
        if st.form_submit_button("Gerar"):
            res = agente_peticao(fat, trib)
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                hist = f"FATOS: {fat} || DATA: {datetime.now()}"
                cur.execute("INSERT INTO processos (cliente_nome, tribunal, status, historico) VALUES (%s,%s,%s,%s)", (cli, trib, "Inicial", hist))
                conn.commit()
                conn.close()
                st.toast("Salvo!")
            except: pass
            st.download_button("Baixar", res, "peticao.txt")

elif menu == "2. Carteira CRM":
    st.header("CRM")
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM processos ORDER BY id DESC", conn)
        st.dataframe(df)
        conn.close()
    except: st.error("Erro DB")

# --- ABA 3: JURIMETRIA GOOGLE (A NOVA LÓGICA) ---
elif menu == "3. Jurimetria (Google Search)":
    st.header("🌎 Investigação Web (Jusbrasil/Escavador)")
    st.info("Buscamos referências reais indexadas pelo Google.")
    
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT cliente_nome, historico, tribunal FROM processos", conn)
        conn.close()
        
        if not df.empty:
            c1, c2 = st.columns(2)
            sel_cli = c1.selectbox("Cliente", df["cliente_nome"])
            
            # Pega dados
            dado = df[df["cliente_nome"] == sel_cli].iloc[0]
            fatos = dado["historico"]
            trib = dado["tribunal"]
            
            st.caption(f"Fatos: {fatos[:100]}...")
            
            juiz = c2.text_input("Nome do Juiz (Sobrenome + Nome):")
            tema = c2.text_input("Palavra-Chave:", value="Dano Moral")
            
            if st.button("🔍 Pesquisar na Web"):
                if juiz:
                    with st.status("Pesquisando...", expanded=True) as s:
                        s.write("Vasculhando Jusbrasil e Tribunais via Google...")
                        
                        # 1. Busca Links Reais
                        resultados = buscar_jurisprudencia_google(juiz, tema, trib)
                        
                        if resultados:
                            s.write(f"Encontrados {len(resultados)} links relevantes.")
                            # Mostra prévia
                            df_res = pd.DataFrame(resultados)
                            st.dataframe(df_res[["titulo", "link"]])
                            
                            # 2. IA Analisa
                            s.write("Gemini está lendo os resumos...")
                            analise = agente_analise_google(resultados, juiz, fatos)
                            
                            st.markdown("---")
                            st.markdown(analise)
                        else:
                            st.warning("Google não retornou resultados específicos. Tente mudar o termo de busca.")
                            
                        s.update(label="Pronto!", state="complete")
                else:
                    st.warning("Digite o Juiz.")
        else:
            st.warning("Cadastre clientes antes.")
            
    except Exception as e: st.error(f"Erro: {e}")
