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
st.set_page_config(page_title="Advogado AI - Precision", layout="wide", page_icon="⚖️")

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

# --- FUNÇÃO DE BUSCA SERPER (MODO ESTRITO) ---
def buscar_google_serper_estrito(nome_alvo, tipo_alvo, tema):
    """
    Busca exata usando aspas e contexto específico (Juiz ou Advogado).
    """
    url = "https://google.serper.dev/search"
    
    # Lógica de Query Especializada
    # Aspas duplas forçam o Google a achar o nome EXATO.
    if tipo_alvo == "Juiz(a)":
        # Ex: site:jusbrasil.com.br "Juiz João Silva" "Dano Moral" sentença
        query_texto = f'site:jusbrasil.com.br "{nome_alvo}" "{tema}" sentença'
    else:
        # Ex: site:jusbrasil.com.br "Advogada Maria Souza" "Dano Moral"
        # Removemos a palavra 'sentença' obrigatória para achar petições ou diários
        query_texto = f'site:jusbrasil.com.br "{nome_alvo}" "{tema}"'
    
    payload = json.dumps({
        "q": query_texto,
        "gl": "br",
        "hl": "pt-br",
        "num": 20 # Buscamos mais resultados para poder filtrar os ruins
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
            
            # FILTRAGEM VIA PYTHON (A "Peneira")
            for item in dados.get("organic", []):
                titulo = item.get("title", "").lower()
                snippet = item.get("snippet", "").lower()
                nome_lower = nome_alvo.lower()
                
                # Só aceita se o nome digitado aparecer LITERALMENTE no título ou resumo
                if nome_lower in titulo or nome_lower in snippet:
                    resultados_filtrados.append({
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
    try:
        return model.generate_content(conteudo, request_options={"timeout": 600}).text
    except Exception as e: return str(e)

def agente_comparativo_jurimetria(lista_resultados, nome_alvo, tipo_alvo, meu_caso_fatos):
    """
    Compara a petição do usuário com os resultados exatos encontrados.
    """
    texto_links = ""
    # Pega apenas os 5 mais relevantes que passaram no filtro
    for r in lista_resultados[:5]: 
        texto_links += f"- Título: {r['titulo']}\n  Resumo: {r['resumo']}\n  Link: {r['link']}\n\n"
        
    prompt = f"""
    ATUE COMO ESTRATEGISTA JURÍDICO SÊNIOR.
    
    1. MEU CASO (FATOS):
    "{meu_caso_fatos}"
    
    2. HISTÓRICO ENCONTRADO DE {nome_alvo} ({tipo_alvo}):
    {texto_links}
    
    TAREFA DE COMPARAÇÃO:
    Você está analisando o histórico desse profissional/juiz.
    
    SAÍDA ESPERADA (Markdown):
    ### 🆚 Comparativo: Meu Caso vs. Histórico
    *   **Contexto:** O(a) {tipo_alvo} já atuou em casos idênticos?
    *   **Análise:** Se for Juiz: Ele julga procedente? Se for Advogado: Qual tese ele costuma usar?
    
    ### 🎯 Probabilidade e Estratégia
    *   **Chance:** (Alta/Média/Baixa).
    *   **Dica Ouro:** O que fazer diferente dos casos listados?
    
    ### 🏆 Melhor Referência
    (Cite o caso mais parecido da lista acima).
    """
    return model.generate_content(prompt).text

def agente_comunicacao(fase, nome):
    return model.generate_content(f"Msg WhatsApp curta para {nome} sobre fase {fase}.").text

# --- INTERFACE ---
st.title("⚖️ Advogado AI - Busca Exata")

menu = st.sidebar.radio("Menu", ["1. Novo Caso", "2. CRM", "3. Jurimetria (Investigação)"])

# ABA 1 - MANTIDA IGUAL
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

# ABA 2 - MANTIDA IGUAL
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

# ABA 3 - JURIMETRIA MELHORADA
elif menu == "3. Jurimetria (Investigação)":
    st.header("🌎 Comparativo Estratégico (Modo Estrito)")
    st.info("Agora filtramos resultados para garantir que seja a pessoa exata.")
    
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
            
            # NOVOS CAMPOS DE CONTROLE
            col_tipo, col_nome = st.columns([1, 2])
            tipo_alvo = col_tipo.selectbox("Quem investigar?", ["Juiz(a)", "Advogado(a)"])
            nome_alvo = col_nome.text_input(f"Nome do {tipo_alvo} (Nome Completo ajuda):")
            tema = st.text_input("Tema (Ex: Dano Moral Telefonia):", value="Dano Moral")
            
            if st.button("🔍 Investigar e Comparar"):
                if nome_alvo:
                    with st.status("Investigação Profunda...", expanded=True) as s:
                        s.write(f"1. Buscando ocorrências exatas de '{nome_alvo}'...")
                        
                        # Busca Filtrada
                        resultados = buscar_google_serper_estrito(nome_alvo, tipo_alvo, tema)
                        
                        if resultados:
                            s.write(f"✅ Filtramos {len(resultados)} resultados onde a pessoa aparece.")
                            st.dataframe(pd.DataFrame(resultados)[['titulo', 'link']])
                            
                            s.write("2. IA Comparando com sua petição...")
                            analise = agente_comparativo_jurimetria(resultados, nome_alvo, tipo_alvo, fatos)
                            
                            st.markdown("---")
                            st.markdown(analise)
                        else:
                            st.warning(f"Não encontrei o nome exato '{nome_alvo}' vinculado ao tema '{tema}' no Jusbrasil. Tente tirar abreviações.")
                        s.update(label="Concluído", state="complete")
                else:
                    st.warning("Digite o Nome.")
        else:
            st.warning("Sem clientes.")
    except Exception as e: st.error(str(e))
