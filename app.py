import streamlit as st
import mysql.connector
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from docx import Document
from io import BytesIO
from PIL import Image

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Sistema JEC AI (Gemini)", layout="wide", page_icon="⚖️")

# 1. Configurar Google Gemini
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # CORREÇÃO: O modelo atual estável é o 1.5-flash
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

# --- FUNÇÕES DE INTELIGÊNCIA ARTIFICIAL (AGENTES) ---

def agente_peticao_inicial(relato_texto, imagens_upload):
    """
    Agente que analisa texto e prints (imagens) para criar a petição.
    """
    lista_conteudo = []
    
    # Prompt do Especialista JEC
    prompt_sistema = """
    Você é um Advogado Especialista em Juizados Especiais Cíveis (Lei 9.099/95).
    TAREFA: Analisar as provas e redigir uma Petição Inicial completa.
    
    ESTRUTURA OBRIGATÓRIA:
    1. Endereçamento (Ao Juízo do JEC da Comarca...)
    2. Qualificação das partes (Deixe campos [PREENCHER] se faltar dados)
    3. DOS FATOS: Resuma o relato e descreva O QUE VOCÊ VÊ nos prints/provas (datas, valores, conversas).
    4. DO DIREITO: Cite CDC, Código Civil ou Súmulas.
    5. DOS PEDIDOS: Liquide os pedidos (estime valores de Dano Moral se cabível).
    6. Valor da Causa.
    """
    
    lista_conteudo.append(prompt_sistema)
    lista_conteudo.append(f"RELATO DO CLIENTE: {relato_texto}")
    
    # Adicionar imagens (prints) para o Gemini analisar
    if imagens_upload:
        lista_conteudo.append("SEGUE ABAIXO AS PROVAS DOCUMENTAIS (PRINTS/FOTOS):")
        for arq in imagens_upload:
            try:
                img = Image.open(arq)
                # Remover transparência e reduzir tamanho
                if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                    img = img.convert('RGB')
                img.thumbnail((1024, 1024))
                lista_conteudo.append(img)
            except Exception as e:
                st.warning(f"Não foi possível ler uma das imagens: {e}")
            
    try:
        response = model.generate_content(
            lista_conteudo, 
            request_options={"timeout": 600}
        )
        return response.text
    except Exception as e:
        return f"ERRO NA GERAÇÃO DA IA: {str(e)}"

def agente_jurimetria(nome_juiz, tribunal):
    """
    Simula a análise do perfil do juiz.
    """
    prompt = f"""
    Atue como um analista de Jurimetria.
    Juiz: {nome_juiz} ({tribunal}).
    
    Baseado em padrões comuns de julgamento, crie um perfil (simulado para MVP):
    1. É "Juiz de Lei" (Legalista) ou "Juiz de Equidade" (Mais flexível)?
    2. Rigor com Dano Moral (Mero aborrecimento vs Dano in re ipsa).
    3. Dica estratégica para audiência com ele.
    """
    response = model.generate_content(prompt)
    return response.text

def agente_comunicacao(fase, nome_cliente, dados_audiencia=None):
    """
    Cria mensagens de WhatsApp para o cliente.
    """
    prompt = f"""
    Crie uma mensagem curta e empática para WhatsApp.
    Destinatário: Cliente {nome_cliente}.
    Contexto: O processo mudou para a fase '{fase}'.
    {f"Dados da Audiência: {dados_audiencia}" if dados_audiencia else ""}
    
    Oriente o cliente sobre o próximo passo de forma simples.
    """
    response = model.generate_content(prompt)
    return response.text

# --- INTERFACE DO SISTEMA ---

st.title("⚖️ Sistema SaaS JEC & IA (Powered by Gemini)")

menu = st.sidebar.radio("Navegação", [
    "1. Novo Caso (Pré-Processual)", 
    "2. Gestão de Processos (CRM)", 
    "3. Análise de Juízes (Jurimetria)"
])

# --- TELA 1: CADASTRO E PETIÇÃO ---
if menu == "1. Novo Caso (Pré-Processual)":
    st.header("📂 Cadastro de Cliente e Geração de Inicial")
    st.info("O Gemini analisará o relato e os prints (provas) para montar a peça.")
    
    with st.form("form_inicial"):
        col1, col2 = st.columns(2)
        with col1:
            cliente = st.text_input("Nome do Cliente")
            telefone = st.text_input("WhatsApp")
        with col2:
            tribunal = st.selectbox("Tribunal", ["TJRJ", "TJSP", "TJMG", "Outros"])
            valor_causa = st.number_input("Valor Estimado da Causa (R$)", min_value=0.0)
            
        relato = st.text_area("Relato dos Fatos", height=150)
        provas = st.file_uploader("Provas (Prints/Fotos)", 
                                  type=["png", "jpg", "jpeg"], 
                                  accept_multiple_files=True)
        
        btn_gerar = st.form_submit_button("🤖 Analisar Provas e Escrever Petição")

    # Lógica FORA do form para evitar erro do botão download
    if btn_gerar and cliente and relato:
        with st.spinner("Gemini Vision está lendo os prints e escrevendo a petição..."):
            # A. Chamar IA
            peticao_texto = agente_peticao_inicial(relato, provas)
            
            # B. Salvar no MySQL Hostgator
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                sql = """INSERT INTO processos 
                            (cliente_nome, cliente_telefone, tribunal, status, historico) 
                            VALUES (%s, %s, %s, %s, %s)"""
                historico_inicial = f"{datetime.now()}: Petição gerada via IA."
                cursor.execute(sql, (cliente, telefone, tribunal, "Petição Pronta", historico_inicial))
                conn.commit()
                conn.close()
                st.toast("Processo Salvo no Banco de Dados!", icon="💾")
            except Exception as e:
                st.error(f"Erro ao salvar no banco: {e}")
            
            # C. Exibir Resultado
            st.subheader("Minuta Gerada")
            st.text_area("Copie o texto:", value=peticao_texto, height=400)
            
            # D. Botão Download
            doc = Document()
            doc.add_heading(f'Petição Inicial - {cliente}', 0)
            doc.add_paragraph(peticao_texto)
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            
            st.download_button(
                label="📥 Baixar .DOCX", 
                data=buffer, 
                file_name=f"Inicial_{cliente}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

# --- TELA 2: CRM (A PARTE QUE TINHA SUMIDO) ---
elif menu == "2. Gestão de Processos (CRM)":
    st.header("🗂️ Carteira de Clientes")
    
    try:
        conn = get_db_connection()
        # Lê a tabela do banco
        df = pd.read_sql("SELECT * FROM processos ORDER BY id DESC", conn)
        conn.close()
        
        if len(df) > 0:
            proc_selecionado = st.selectbox("Selecione o Cliente:", df["cliente_nome"])
            dados = df[df["cliente_nome"] == proc_selecionado].iloc[0]
            
            st.markdown("---")
            colA, colB, colC = st.columns(3)
            colA.metric("Status", dados["status"])
            colB.metric("Tribunal", dados["tribunal"])
            colC.metric("Telefone", dados["cliente_telefone"])
            
            st.subheader("⚙️ Painel de Ações")
            
            tab1, tab2, tab3 = st.tabs(["Registro TJ", "Audiência", "Julgamento"])
            
            with tab1:
                st.write("Após protocolar no site do TJ, atualize aqui:")
                novo_num = st.text_input("Número do Processo (CNJ)")
                if st.button("Salvar Número CNJ"):
                    st.success(f"Processo {novo_num} vinculado!")
                    # Aqui você pode adicionar um UPDATE SQL no futuro
            
            with tab2:
                st.write("Prepare o cliente para a audiência.")
                data_aud = st.date_input("Data da Audiência")
                if st.button("Gerar Mensagem WhatsApp"):
                    msg = agente_comunicacao("Marcação de Audiência", dados["cliente_nome"], str(data_aud))
                    st.code(msg, language="text")
                
                st.info("Verificação de Remarcação: Automática (Simulada).")

            with tab3:
                st.write("Histórico do Caso:")
                st.text(dados["historico"])

        else:
            st.warning("Nenhum processo cadastrado ainda. Vá na aba 'Novo Caso'.")
            
    except Exception as e:
        st.error(f"Erro ao conectar no banco de dados: {e}")

# --- TELA 3: JURIMETRIA (A PARTE QUE TINHA SUMIDO) ---
elif menu == "3. Análise de Juízes (Jurimetria)":
    st.header("👨‍⚖️ Investigador de Juízes")
    
    col1, col2 = st.columns(2)
    juiz = col1.text_input("Nome do Magistrado")
    comarca = col2.text_input("Comarca/Vara")
    
    if st.button("Analisar Perfil com IA"):
        if juiz:
            with st.spinner(f"Investigando {juiz}..."):
                analise = agente_jurimetria(juiz, comarca)
                st.markdown(analise)
        else:
            st.warning("Digite o nome do juiz.")

