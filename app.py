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
import time # Importante para esperar o erro passar

# --- CONFIGURAÇÕES ---
st.set_page_config(page_title="Advogado AI - Final", layout="wide", page_icon="⚖️")

# 1. Configurar Gemini
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # CORREÇÃO: Usar o modelo 1.5-flash que é o estável e gratuito
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

# --- FUNÇÃO AUXILIAR: RETRY (EVITA ERRO 429) ---
def gerar_conteudo_seguro(conteudo_prompt):
    """
    Tenta gerar conteúdo. Se der erro de cota (429), espera 5 segundos e tenta de novo.
    """
    tentativas = 3
    for i in range(tentativas):
        try:
            # Timeout de 10 minutos para petições longas
            response = model.generate_content(conteudo_prompt, request_options={"timeout": 600})
            return response.text
        except Exception as e:
            erro_str = str(e)
            if "429" in erro_str or "Quota exceeded" in erro_str:
                if i < tentativas - 1: # Se não for a última tentativa
                    st.toast(f"⏳ Alto tráfego na IA. Aguardando 5s para tentar novamente... ({i+1}/{tentativas})", icon="⚠️")
                    time.sleep(5) # Espera 5 segundos
                    continue
                else:
                    return "Erro: O limite da IA foi atingido. Aguarde 1 minuto e tente novamente."
            else:
                return f"Erro na IA: {erro_str}"

# --- FUNÇÃO DE BUSCA SERPER ---
def buscar_google_serper_estrito(nome_alvo, tipo_alvo, tema):
    url = "https://google.serper.dev/search"
    
    if tipo_alvo == "Juiz(a)":
        query_texto = f'site:jusbrasil.com.br "{nome_alvo}" "{tema}" sentença'
    else:
        query_texto = f'site:jusbrasil.com.br "{nome_alvo}" "{tema}"'
    
    payload = json.dumps({
        "q": query_texto,
        "gl": "br",
        "hl": "pt-br",
        "num": 20
    })
    
    headers = {
        'X-API-KEY': st.secrets["SERPER_API_KEY"],
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.request("POST", url, headers=headers, data=payload)
        if response.status_code == 200:
            dados = response.json()
            resultados_filtrados = []
            
            # Regex para Número de Processo CNJ
            padrao_cnj = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
            
            for item in dados.get("organic", []):
                titulo = item.get("title", "").lower()
                snippet = item.get("snippet", "").lower()
                nome_lower = nome_alvo.lower()
                
                if nome_lower in titulo or nome_lower in snippet:
                    texto_completo = item.get("title", "") + " " + item.get("snippet", "")
                    match_proc = re.search(padrao_cnj, texto_completo)
                    numero_proc = match_proc.group() if match_proc else "Ver no Link"
                    
                    resultados_filtrados.append({
                        "processo": numero_proc,
                        "titulo": item.get("title"),
                        "link": item.get("link"),
                        "resumo": item.get("snippet")
                    })
            return resultados_filtrados
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
            
    # Usa a função segura com retry
    return gerar_conteudo_seguro(conteudo)

def agente_comparativo_jurimetria(lista_resultados, nome_alvo, tipo_alvo, meu_caso_fatos):
    texto_links = ""
    for r in lista_resultados[:5]: 
        texto_links += f"- PROCESSO: {r['processo']}\n  Título: {r['titulo']}\n  Resumo: {r['resumo']}\n  Link: {r['link']}\n\n"
        
    prompt = f"""
    ATUE COMO ESTRATEGISTA JURÍDICO SÊNIOR.
    
    1. MEU CASO (FATOS):
    "{meu_caso_fatos}"
    
    2. DADOS ENCONTRADOS DE {nome_alvo} ({tipo_alvo}):
    {texto_links}
    
    TAREFA:
    Compare meu caso com o histórico encontrado.
    
    SAÍDA OBRIGATÓRIA (Markdown):
    
    ### 🆚 Análise Comparativa
    (Como o meu caso se parece com os encontrados?)
    
    ### 🎯 Probabilidade e Risco
    (Chance de Êxito e Pontos de Atenção).
    
    ### 🏆 Referência (Processo Paradigma)
    *   **Nº do Processo:** (Cite o número do processo listado acima. Se estiver 'Ver no Link', diga isso).
    *   **Resumo:** (O que aconteceu nesse processo).
    *   **Aplicação:** (Como usar isso a nosso favor).
    """
    return gerar_conteudo_seguro(prompt)

def agente_comunicacao(fase, nome):
    return gerar_conteudo_seguro(f"Msg WhatsApp curta para {nome} sobre fase {fase}.")

# --- INTERFACE ---
st.title("⚖️ Advogado AI - Sistema Final")

menu = st.sidebar.radio("Menu", ["1. Novo Caso", "2. CRM", "3. Jurimetria (Investigação)"])

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

# ABA 3
elif menu == "3. Jurimetria (Investigação)":
    st.header("🌎 Comparativo Estratégico")
    st.info("Buscando Precedentes com Números de Processo (CNJ).")
    
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT cliente_nome, historico FROM processos", conn)
        conn.close()
        
        if not df.empty:
            c1, c2 = st.columns(2)
            sel_cli = c1.selectbox("Selecione seu Cliente:", df["cliente_nome"])
            dado = df[df["cliente_nome"] == sel_cli].iloc[0]
            
            fatos = dado["historico"]
            if "FATOS:" in fatos: fatos = fatos.split("FATOS:")[1].split("||")[0]
            
            st.write(f"**Caso:** _{fatos[:100]}..._")
            
            col_tipo, col_nome = st.columns([1, 2])
            tipo_alvo = col_tipo.selectbox("Quem investigar?", ["Juiz(a)", "Advogado(a)"])
            nome_alvo = col_nome.text_input(f"Nome do {tipo_alvo}:")
            tema = st.text_input("Tema:", value="Dano Moral")
            
            if st.button("🔍 Investigar e Comparar"):
                if nome_alvo:
                    with st.status("Processando...", expanded=True) as s:
                        s.write(f"1. Buscando ocorrências de '{nome_alvo}'...")
                        
                        resultados = buscar_google_serper_estrito(nome_alvo, tipo_alvo, tema)
                        
                        if resultados:
                            s.write(f"✅ Encontrados {len(resultados)} resultados.")
                            df_res = pd.DataFrame(resultados)
                            st.dataframe(df_res[['processo', 'titulo', 'link']])
                            
                            s.write("2. IA Comparando...")
                            analise = agente_comparativo_jurimetria(resultados, nome_alvo, tipo_alvo, fatos)
                            
                            st.markdown("---")
                            st.markdown(analise)
                        else:
                            st.warning(f"Não encontrei resultados exatos.")
                        s.update(label="Concluído", state="complete")
                else:
                    st.warning("Digite o Nome.")
        else:
            st.warning("Sem clientes.")
    except Exception as e: st.error(str(e))
