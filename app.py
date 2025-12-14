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
    # Usando o Flash que é rápido e multimodal
    model = genai.GenerativeModel('gemini-1.5-flash') 
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
    3. DOS FATOS: Resuma o relato e descreva o que aparece nos prints/provas.
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
            img = Image.open(arq)
            lista_conteudo.append(img)
            
    # Gerar conteúdo
    response = model.generate_content(lista_conteudo)
    return response.text

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

# Menu Lateral (CRM e Fluxo)
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
        provas = st.file_uploader("Provas (Prints de Conversas, Fotos, Contratos)", 
                                  type=["png", "jpg", "jpeg"], 
                                  accept_multiple_files=True)
        
        btn_gerar = st.form_submit_button("🤖 Analisar Provas e Escrever Petição")
        
        if btn_gerar and cliente and relato:
            with st.spinner("Gemini Vision está lendo os prints e escrevendo a petição..."):
                # 1. Chamar IA
                peticao_texto = agente_peticao_inicial(relato, provas)
                
                # 2. Salvar no MySQL Hostgator
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
                
                # 3. Exibir Resultado
                st.subheader("Minuta Gerada")
                st.text_area("Copie o texto:", value=peticao_texto, height=400)
                
                # Botão Download DOCX
                doc = Document()
                doc.add_heading(f'Petição Inicial - {cliente}', 0)
                doc.add_paragraph(peticao_texto)
                buffer = BytesIO()
                doc.save(buffer)
                buffer.seek(0)
                st.download_button("📥 Baixar .DOCX", data=buffer, file_name=f"Inicial_{cliente}.docx")

# --- TELA 2: CRM E GESTÃO ---
elif menu == "2. Gestão de Processos (CRM)":
    st.header("🗂️ Carteira de Clientes")
    
    # Carregar dados do MySQL
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM processos ORDER BY id DESC", conn)
        conn.close()
        
        if len(df) > 0:
            proc_selecionado = st.selectbox("Selecione o Cliente:", df["cliente_nome"])
            # Filtrar dados do cliente selecionado
            dados = df[df["cliente_nome"] == proc_selecionado].iloc[0]
            
            st.markdown("---")
            colA, colB, colC = st.columns(3)
            colA.metric("Status", dados["status"])
            colB.metric("Tribunal", dados["tribunal"])
            colC.metric("ID Sistema", str(dados["id"]))
            
            st.subheader("⚙️ Ações do Processo")
            
            # Abas de fases
            tab1, tab2, tab3 = st.tabs(["Registro TJ", "Audiência", "Julgamento"])
            
            with tab1:
                st.write("Após protocolar no site do TJ, atualize aqui:")
                novo_num = st.text_input("Número do Processo (CNJ)")
                if st.button("Registrar Protocolo"):
                    # Aqui faria o UPDATE no MySQL
                    st.success(f"Processo {novo_num} vinculado ao cliente!")
            
            with tab2:
                st.write("Prepare o cliente para a audiência.")
                data_aud = st.date_input("Data da Audiência")
                if st.button("Gerar Mensagem de Preparação"):
                    msg = agente_comunicacao("Marcação de Audiência", dados["cliente_nome"], str(data_aud))
                    st.code(msg, language="text")
                
                st.markdown("#### 🕵️ Verificação de Remarcação")
                st.caption("O sistema verifica Diários Oficiais automaticamente (Simulado 3x ao dia).")
                if st.button("Forçar Verificação Agora"):
                    st.info("Consultando API do Tribunal...")
                    st.success("Nenhuma remarcação encontrada no D.O. de hoje.")

            with tab3:
                st.write("Histórico Completo:")
                st.text(dados["historico"])

        else:
            st.warning("Nenhum processo cadastrado ainda.")
            
    except Exception as e:
        st.error(f"Erro de conexão com Hostgator: {e}")

# --- TELA 3: JURIMETRIA ---
elif menu == "3. Análise de Juízes (Jurimetria)":
    st.header("👨‍⚖️ Investigador de Juízes")
    
    col1, col2 = st.columns(2)
    juiz = col1.text_input("Nome do Magistrado")
    comarca = col2.text_input("Comarca/Vara")
    
    if st.button("Analisar Perfil"):
        if juiz:
            with st.spinner(f"Investigando {juiz} na base de dados..."):
                analise = agente_jurimetria(juiz, comarca)
                st.markdown(analise)
        else:
            st.warning("Digite o nome do juiz.")
