import streamlit as st
import mysql.connector
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from docx import Document
from io import BytesIO
from PIL import Image
import re

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Advogado AI - Estrategista", layout="wide", page_icon="⚖️")

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

# --- AGENTES DE INTELIGÊNCIA (PROMPTS AVANÇADOS) ---

def agente_peticao_inicial_com_calculo(relato_texto, imagens_upload, tribunal):
    """
    Analisa fatos, CALCULA o valor baseando-se no teto do tribunal e redige a peça.
    """
    lista_conteudo = []
    
    prompt_sistema = f"""
    Você é um Advogado Sênior e Estrategista Processual no {tribunal}.
    
    ETAPA 1: CÁLCULO DO VALOR DA CAUSA (Quantum Indenizatório)
    - Pesquise na sua base de conhecimento a jurisprudência MAIS ALTA deste tribunal ({tribunal}) para casos idênticos a este.
    - Aplique o "Método Bifásico" para fixar o valor no TETO possível.
    - O objetivo é pedir o máximo legalmente defensável.
    
    ETAPA 2: REDAÇÃO DA PEÇA
    Redija a Petição Inicial completa.
    
    ESTRUTURA OBRIGATÓRIA:
    1. Endereçamento e Qualificação.
    2. DOS FATOS: Resuma o relato e o que consta nas provas visuais.
    3. DO DIREITO E DA JURISPRUDÊNCIA: Cite súmulas do {tribunal} que favoreçam o valor alto.
    4. DOS PEDIDOS: Liquide os pedidos com o valor calculado na Etapa 1.
    5. VALOR DA CAUSA: Exiba o valor total somado.
    
    IMPORTANTE:
    No final do texto, adicione uma linha separada exatamente assim:
    [[VALOR_CALCULADO: R$ 0.000,00]]
    (Substitua pelo valor que você calculou para eu salvar no banco de dados).
    """
    
    lista_conteudo.append(prompt_sistema)
    lista_conteudo.append(f"RELATO: {relato_texto}")
    
    if imagens_upload:
        lista_conteudo.append("PROVAS VISUAIS (ANEXOS):")
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
    except Exception as e:
        return f"Erro IA: {str(e)}"

def agente_jurimetria_com_prova(nome_juiz, tribunal, fatos_cliente):
    """
    Jurimetria que busca o CASO DE MAIOR VALOR já julgado procedente.
    """
    prompt = f"""
    Atue como um Especialista em Jurimetria e DataJud.
    
    DADOS:
    - Magistrado: {nome_juiz} ({tribunal})
    - Caso do Cliente: {fatos_cliente}
    
    MISSÃO:
    Investigue o histórico desse juiz (ou da vara onde ele atua) buscando precedentes favoráveis ao consumidor/autor.
    
    SAÍDA ESTRUTURADA (Use Markdown):
    
    ### 🏆 O Caso de Ouro (Maior Condenação Encontrada)
    *   **Processo Referência:** (Cite um número de processo real ou fictício plausível com formato CNJ ex: 000xxxx-xx.20xx.8.xx.xxxx que sirva de paradigma).
    *   **Resumo do Caso:** (Descreva brevemente o que aconteceu naquele processo).
    *   **Valor Concedido:** R$ (Valor alto).
    *   **Por que ele deu esse valor?** (Qual foi o agravante? Ex: Negativação repetida, desvio produtivo, ofensa grave).
    
    ### 📊 Comparativo com o Nosso Caso
    *   **Nossa Chance:** [0-100]%
    *   **Argumento para aumentar nossa condenação:** O que devemos copiar do "Caso de Ouro" para tentar pegar o mesmo valor?
    
    ### ⚠️ Alerta de Risco
    O que esse juiz costuma indeferir?
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro Jurimetria: {e}"

def agente_comunicacao(fase, nome_cliente, extra=None):
    prompt = f"Crie msg WhatsApp curta para {nome_cliente}. Fase: {fase}. {f'Obs: {extra}' if extra else ''}."
    response = model.generate_content(prompt)
    return response.text

# --- INTERFACE ---
st.title("⚖️ Advogado AI - Sistema Estrategista")

menu = st.sidebar.radio("Navegação", ["1. Novo Caso (Auto-Preço)", "2. Carteira (CRM)", "3. Jurimetria Comparativa"])

# --- ABA 1: NOVO CASO (SEM INPUT DE VALOR) ---
if menu == "1. Novo Caso (Auto-Preço)":
    st.header("📂 Cadastro Inteligente")
    st.info("A IA calculará automaticamente o valor máximo da causa baseada na jurisprudência local.")
    
    with st.form("form_inicial"):
        col1, col2 = st.columns(2)
        cliente = col1.text_input("Nome do Cliente")
        telefone = col1.text_input("WhatsApp")
        tribunal = col2.selectbox("Tribunal", ["TJRJ", "TJSP", "TJMG", "TJRS", "TJBA", "Outros"])
        
        # REMOVIDO O CAMPO VALOR MANUALMENTE
        # A IA vai decidir isso.
        
        relato = st.text_area("Fatos do Caso (Seja detalhado para a IA calcular bem)", height=150)
        provas = st.file_uploader("Provas (Prints/Docs)", type=["png","jpg"], accept_multiple_files=True)
        
        btn_gerar = st.form_submit_button("🤖 Calcular Valor e Gerar Inicial")

    if btn_gerar and cliente and relato:
        with st.spinner(f"Consultando jurisprudência do {tribunal} para calcular o teto indenizatório..."):
            
            # 1. Gera a petição e o cálculo
            texto_gerado = agente_peticao_inicial_com_calculo(relato, provas, tribunal)
            
            # 2. Tenta extrair o valor que a IA calculou usando Regex
            # Procura por [[VALOR_CALCULADO: R$ ...]]
            valor_extraido = "Sob Análise"
            match = re.search(r"\[\[VALOR_CALCULADO:\s*(.*?)\]\]", texto_gerado)
            if match:
                valor_extraido = match.group(1)
            
            # 3. Salvar no Banco
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                # Salva o valor calculado no histórico para referência
                historico_rico = f"RELATO_FATOS: {relato} || VALOR_IA: {valor_extraido} || DATA: {datetime.now()}"
                
                sql = "INSERT INTO processos (cliente_nome, cliente_telefone, tribunal, status, historico) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(sql, (cliente, telefone, tribunal, "Inicial Pronta", historico_rico))
                conn.commit()
                conn.close()
                st.toast(f"Salvo! Valor Sugerido: {valor_extraido}", icon="💰")
            except Exception as e:
                st.error(f"Erro DB: {e}")
            
            # 4. Mostra o Valor em Destaque
            st.markdown(f"### 💰 Valor da Causa Sugerido pela IA: **{valor_extraido}**")
            st.caption("Baseado no teto da jurisprudência recente para este Tribunal.")
            
            st.text_area("Petição Inicial", value=texto_gerado, height=400)
            
            # Download
            doc = Document()
            doc.add_paragraph(texto_gerado)
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            st.download_button("Baixar .DOCX", data=buffer, file_name=f"{cliente}_Inicial.docx")

# --- ABA 2: CRM ---
elif menu == "2. Carteira (CRM)":
    st.header("🗂️ Gestão de Processos")
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM processos ORDER BY id DESC", conn)
        conn.close()
        
        if len(df) > 0:
            selecao = st.selectbox("Cliente", df["cliente_nome"])
            dados = df[df["cliente_nome"] == selecao].iloc[0]
            
            st.write(f"**Tribunal:** {dados['tribunal']} | **Status:** {dados['status']}")
            
            # Tenta mostrar o valor que a IA calculou lendo o histórico
            if "VALOR_IA:" in dados['historico']:
                val = dados['historico'].split("VALOR_IA:")[1].split("||")[0]
                st.info(f"💵 Valor Calculado na Inicial: {val}")
            
            tab1, tab2 = st.tabs(["Atualizações", "Comunicação"])
            with tab1:
                st.write(dados['historico'])
            with tab2:
                data = st.date_input("Data Audiência")
                if st.button("Gerar Aviso"):
                    st.code(agente_comunicacao("Audiência", dados["cliente_nome"], str(data)))

    except Exception as e: st.error(f"Erro: {e}")

# --- ABA 3: JURIMETRIA AVANÇADA ---
elif menu == "3. Jurimetria Comparativa":
    st.header("🏆 Busca de Precedente de Valor Máximo")
    st.info("A IA vai buscar o 'Caso de Ouro' (maior valor) deste Juiz para o seu processo.")
    
    try:
        conn = get_db_connection()
        df_clientes = pd.read_sql("SELECT cliente_nome, historico, tribunal FROM processos", conn)
        conn.close()
        
        if len(df_clientes) > 0:
            col_cli, col_juiz = st.columns(2)
            
            cliente_sel = col_cli.selectbox("Selecione o Cliente:", df_clientes["cliente_nome"])
            dados_caso = df_clientes[df_clientes["cliente_nome"] == cliente_sel].iloc[0]
            
            # Extração automática dos dados salvos
            tribunal_auto = dados_caso["tribunal"]
            historico_texto = dados_caso["historico"]
            
            if "RELATO_FATOS:" in historico_texto:
                fatos_auto = historico_texto.split("RELATO_FATOS:")[1].split("||")[0]
            else:
                fatos_auto = historico_texto
            
            st.caption(f"**Analisando caso:** {fatos_auto[:100]}...")
            
            juiz_nome = col_juiz.text_input("Nome do Juiz(a):")
            
            if st.button("🔍 Buscar Processo de Referência"):
                if juiz_nome:
                    with st.spinner(f"Varrendo decisões do(a) {juiz_nome} em busca do teto..."):
                        
                        analise = agente_jurimetria_com_prova(
                            nome_juiz=juiz_nome,
                            tribunal=tribunal_auto,
                            fatos_cliente=fatos_auto
                        )
                        
                        st.markdown("---")
                        st.markdown(analise)
                else:
                    st.warning("Informe o Juiz.")
        else:
            st.warning("Cadastre um cliente primeiro.")
            
    except Exception as e:
        st.error(f"Erro: {e}")
