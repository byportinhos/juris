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

# --- CONFIGURAÇÕES ---
st.set_page_config(page_title="Advogado AI - Pro", layout="wide", page_icon="⚖️")

# 1. Configurar Gemini
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash') 
except:
    st.error("ERRO: Configure a GOOGLE_API_KEY nos Secrets.")
    st.stop()

# 2. Conexão DB
def get_db_connection():
    return mysql.connector.connect(
        host=st.secrets["database"]["DB_HOST"],
        user=st.secrets["database"]["DB_USER"],
        password=st.secrets["database"]["DB_PASS"],
        database=st.secrets["database"]["DB_NAME"]
    )

# --- FUNÇÃO DE BUSCA PROFISSIONAL (SERPER.DEV) ---
def buscar_google_serper(nome_juiz, tema):
    """
    Usa a API Serper para fazer buscas no Google sem ser bloqueado.
    """
    url = "https://google.serper.dev/search"
    
    # Query focada em achar sentenças no Jusbrasil
    # Ex: "Sentença Juiz João da Silva Dano Moral site:jusbrasil.com.br"
    query_texto = f'Sentença Juiz {nome_juiz} "{tema}" site:jusbrasil.com.br'
    
    payload = json.dumps({
        "q": query_texto,
        "gl": "br", # País: Brasil
        "hl": "pt-br", # Idioma: Português
        "num": 10 # 10 Resultados
    })
    
    headers = {
        'X-API-KEY': st.secrets["SERPER_API_KEY"],
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
        if response.status_code == 200:
            dados = response.json()
            resultados = []
            
            # Processa os resultados orgânicos
            for item in dados.get("organic", []):
                resultados.append({
                    "titulo": item.get("title"),
                    "link": item.get("link"),
                    "resumo": item.get("snippet") # O resumo que o Google mostra
                })
            return resultados
        else:
            st.error(f"Erro Serper: {response.text}")
            return []
    except Exception as e:
        st.error(f"Erro conexão: {e}")
        return []

# --- AGENTES DE INTELIGÊNCIA ---

def agente_peticao_multimodal(relato, imagens, tribunal):
    conteudo = []
    prompt = f"""
    Você é um Advogado Sênior.
    1. Analise o relato e IMAGENS.
    2. Calcule valor da causa (Teto do {tribunal}).
    3. Redija a Inicial.
    4. Fim: [[VALOR_CALCULADO: R$ ...]]
    """
    conteudo.append(prompt)
    conteudo.append(f"RELATO: {relato}")
    if imagens:
        conteudo.append("PROVAS:")
        for arq in imagens:
            try:
                img = Image.open(arq)
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info): img = img.convert('RGB')
                img.thumbnail((1024, 1024))
                conteudo.append(img)
            except: pass
    try:
        return model.generate_content(conteudo, request_options={"timeout": 600}).text
    except Exception as e: return str(e)

def agente_comparativo_jurimetria(lista_resultados, nome_juiz, meu_caso_fatos):
    """
    COMPARA a petição do usuário com os resumos encontrados.
    """
    texto_links = ""
    for r in lista_resultados[:5]: 
        texto_links += f"- Título: {r['titulo']}\n  Resumo do Google: {r['resumo']}\n  Link: {r['link']}\n\n"
        
    prompt = f"""
    ATUE COMO ESTRATEGISTA JURÍDICO SÊNIOR.
    
    1. MEU CASO (FATOS DA MINHA PETIÇÃO):
    "{meu_caso_fatos}"
    
    2. O QUE O JUIZ {nome_juiz} JÁ DECIDIU (BUSCA GOOGLE):
    {texto_links}
    
    TAREFA DE COMPARAÇÃO (IMPORTANTE):
    Você deve comparar os fatos do meu caso com os resumos das sentenças encontradas.
    
    SAÍDA ESPERADA (Markdown):
    ### 🆚 Comparativo: Meu Caso vs. Precedentes
    *   **Similaridade:** Os casos encontrados são parecidos com o meu? (Sim/Não e Porquê).
    *   **Ponto de Atenção:** O resumo do Google mostra que ele julgou improcedente algum caso parecido? Por qual motivo?
    
    ### 🎯 Probabilidade e Estratégia
    *   **Chance de Vitória:** (Alta/Média/Baixa) baseada no histórico acima.
    *   **Dica:** O que devo adicionar na minha petição para não cair no mesmo erro dos casos improcedentes?
    
    ### 🏆 Melhor Jurisprudência Encontrada
    (Copie o Link e o Título do caso mais favorável para eu usar).
    """
    return model.generate_content(prompt).text

def agente_comunicacao(fase, nome):
    return model.generate_content(f"Msg WhatsApp curta para {nome} sobre fase {fase}.").text

# --- INTERFACE ---
st.title("⚖️ Advogado AI - Comparativo Real")

menu = st.sidebar.radio("Menu", ["1. Novo Caso", "2. CRM", "3. Jurimetria (Google IA)"])

# ABA 1
if menu == "1. Novo Caso":
    st.header("📂 Cadastro")
    with st.form("f1"):
        c1, c2 = st.columns(2)
        cli = c1.text_input("Cliente")
        tel = c1.text_input("WhatsApp")
        trib = c2.selectbox("Tribunal", ["TJRJ", "TJSP", "TJMG", "Outros"])
        relato = st.text_area("Fatos")
        arquivos = st.file_uploader("Provas", type=["png","jpg"], accept_multiple_files=True)
        btn = st.form_submit_button("Gerar Inicial")

    if btn and cli and relato:
        with st.spinner("Gerando..."):
            res = agente_peticao_multimodal(relato, arquivos, trib)
            val = "A Calcular"
            match = re.search(r"\[\[VALOR_CALCULADO:\s*(.*?)\]\]", res)
            if match: val = match.group(1)
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                hist = f"FATOS: {relato} || VALOR: {val} || DATA: {datetime.now()}"
                if arquivos: hist += " || [COM IMAGENS]"
                cur.execute("INSERT INTO processos (cliente_nome, cliente_telefone, tribunal, status, historico) VALUES (%s,%s,%s,%s,%s)", (cli, tel, trib, "Inicial", hist))
                conn.commit()
                conn.close()
                st.toast(f"Salvo! {val}")
            except Exception as e: st.error(str(e))
            st.markdown(f"### 💰 {val}")
            st.download_button("Baixar", res, f"{cli}.txt")

# ABA 2
elif menu == "2. CRM":
    st.header("🗂️ CRM")
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM processos ORDER BY id DESC", conn)
        conn.close()
        if not df.empty:
            sel = st.selectbox("Cliente", df["cliente_nome"])
            d = df[df["cliente_nome"] == sel].iloc[0]
            st.write(d['historico'])
            if st.button("Msg Zap"): st.code(agente_comunicacao("Audiência", sel))
    except: pass

# ABA 3 (JURIMETRIA SERPER)
elif menu == "3. Jurimetria (Google IA)":
    st.header("🌎 Comparativo de Tese (Google Search)")
    st.info("A IA vai ler os resultados do Jusbrasil e comparar com o seu caso.")
    
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT cliente_nome, historico FROM processos", conn)
        conn.close()
        
        if not df.empty:
            c1, c2 = st.columns(2)
            sel_cli = c1.selectbox("Selecione seu Cliente:", df["cliente_nome"])
            dado = df[df["cliente_nome"] == sel_cli].iloc[0]
            
            # Recupera os fatos da petição salva
            fatos = dado["historico"]
            if "FATOS:" in fatos: fatos = fatos.split("FATOS:")[1].split("||")[0]
            
            st.write(f"**Analisando Tese do Cliente:** _{fatos[:150]}..._")
            
            juiz = c2.text_input("Nome do Juiz (Ex: João da Silva):")
            tema = c2.text_input("Tema (Ex: Dano Moral):", value="Dano Moral")
            
            if st.button("🔍 Comparar com Jurisprudência"):
                if juiz:
                    with st.status("Processando...", expanded=True) as s:
                        s.write("1. Buscando sentenças no Google (API Serper)...")
                        # Busca Garantida (Sem bloqueio)
                        resultados = buscar_google_serper(juiz, tema)
                        
                        if resultados:
                            s.write(f"✅ Encontrados {len(resultados)} casos relevantes.")
                            st.dataframe(pd.DataFrame(resultados)[['titulo', 'link']])
                            
                            s.write("2. Gemini está lendo e comparando com sua petição...")
                            analise = agente_comparativo_jurimetria(resultados, juiz, fatos)
                            
                            st.markdown("---")
                            st.markdown(analise)
                        else:
                            st.warning("Não encontrei resultados exatos no Jusbrasil.")
                        s.update(label="Concluído", state="complete")
                else:
                    st.warning("Digite o Juiz")
        else:
            st.warning("Sem clientes.")
    except Exception as e: st.error(str(e))

