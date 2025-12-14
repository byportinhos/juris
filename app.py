import streamlit as st
import mysql.connector
import google.generativeai as genai
from datetime import datetime
import pandas as pd
from docx import Document
from io import BytesIO
from PIL import Image

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="Sistema JEC AI - Jurimetria Avançada", layout="wide", page_icon="⚖️")

# 1. Configurar Google Gemini
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
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
    lista_conteudo = []
    prompt_sistema = """
    Você é um Advogado Especialista em JEC. Analise as provas e redija a Inicial.
    ESTRUTURA: Endereçamento, Qualificação, DOS FATOS (Descreva o que vê nos prints), DO DIREITO, PEDIDOS (Com valores), Valor da Causa.
    """
    lista_conteudo.append(prompt_sistema)
    lista_conteudo.append(f"RELATO: {relato_texto}")
    
    if imagens_upload:
        lista_conteudo.append("PROVAS (PRINTS):")
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

def agente_jurimetria_casada(nome_juiz, tribunal, fatos_cliente, valor_pedido):
    """
    Jurimetria Avançada: Cruza o perfil do juiz COM o caso específico do cliente.
    """
    prompt = f"""
    Atue como um Especialista em Jurimetria e Estratégia Processual.
    
    DADOS DA ANÁLISE:
    1. MAGISTRADO: {nome_juiz} ({tribunal})
    2. CASO DO CLIENTE: {fatos_cliente}
    3. VALOR PEDIDO NA INICIAL: R$ {valor_pedido}
    
    TAREFA: Simule uma análise preditiva cruzando o perfil deste juiz com este tipo específico de caso.
    
    SAÍDA ESPERADA (Seja realista e duro, use formatação Markdown):
    
    ### 🎯 Probabilidade de Êxito
    [Dê uma porcentagem estimada e explique o porquê baseada no perfil do juiz para esse tema]
    
    ### ⚖️ Régua de Valores (Quantum Indenizatório)
    *   **Média deste Juiz para casos similares:** R$ [Valor]
    *   **Teto Máximo já visto:** R$ [Valor]
    *   **Risco:** [Existe risco de improcedência ou mero aborrecimento?]
    
    ### 🆚 Comparativo: Sua Petição vs. Cabeça do Juiz
    *   **Ponto Forte do seu caso para este juiz:** [O que vai convencer ELE?]
    *   **Ponto Fraco:** [O que ele costuma indeferir?]
    
    ### 💡 Recomendação Estratégica
    [Dica prática para a audiência ou para a réplica]
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Erro na análise jurimétrica: {e}"

def agente_comunicacao(fase, nome_cliente, dados_audiencia=None):
    prompt = f"Crie msg WhatsApp para cliente {nome_cliente}. Fase: {fase}. {f'Audiência: {dados_audiencia}' if dados_audiencia else ''}. Seja breve."
    response = model.generate_content(prompt)
    return response.text

# --- INTERFACE ---
st.title("⚖️ Sistema SaaS JEC & IA")

menu = st.sidebar.radio("Navegação", ["1. Novo Caso", "2. CRM", "3. Jurimetria Preditiva"])

# --- ABA 1: NOVO CASO ---
if menu == "1. Novo Caso":
    st.header("📂 Cadastro e Inicial")
    with st.form("form_inicial"):
        col1, col2 = st.columns(2)
        cliente = col1.text_input("Cliente")
        telefone = col1.text_input("WhatsApp")
        tribunal = col2.selectbox("Tribunal", ["TJRJ", "TJSP", "TJMG", "Outros"])
        valor_causa = col2.number_input("Valor da Causa (R$)", min_value=0.0)
        relato = st.text_area("Fatos", height=150)
        provas = st.file_uploader("Provas", type=["png","jpg"], accept_multiple_files=True)
        btn_gerar = st.form_submit_button("🤖 Gerar Inicial")

    if btn_gerar and cliente and relato:
        with st.spinner("IA Trabalhando..."):
            peticao = agente_peticao_inicial(relato, provas)
            
            # ATENÇÃO: Salvamos o RELATO no histórico para usar na Jurimetria depois
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                # Concatenamos o relato no histórico para recuperar fácil depois
                historico_rico = f"RELATO_FATOS: {relato} || DATA: {datetime.now()}"
                sql = "INSERT INTO processos (cliente_nome, cliente_telefone, tribunal, status, historico) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(sql, (cliente, telefone, tribunal, "Inicial Pronta", historico_rico))
                conn.commit()
                conn.close()
                st.toast("Salvo!", icon="✅")
            except Exception as e:
                st.error(f"Erro DB: {e}")
            
            st.text_area("Petição", value=peticao, height=400)
            
            doc = Document()
            doc.add_paragraph(peticao)
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            st.download_button("Baixar Docx", data=buffer, file_name=f"{cliente}.docx")

# --- ABA 2: CRM ---
elif menu == "2. CRM":
    st.header("🗂️ Gestão")
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT * FROM processos ORDER BY id DESC", conn)
        conn.close()
        
        if len(df) > 0:
            selecao = st.selectbox("Cliente", df["cliente_nome"])
            dados = df[df["cliente_nome"] == selecao].iloc[0]
            st.write(f"**Status:** {dados['status']} | **Tribunal:** {dados['tribunal']}")
            
            tab1, tab2 = st.tabs(["Audiência", "Comunicação"])
            with tab1:
                data = st.date_input("Data Audiência")
                if st.button("Gerar Aviso"):
                    st.code(agente_comunicacao("Audiência Marcada", dados["cliente_nome"], str(data)))
            with tab2:
                st.text(dados["historico"])
    except: st.error("Erro conexão DB")

# --- ABA 3: JURIMETRIA AVANÇADA (NOVA LÓGICA) ---
elif menu == "3. Jurimetria Preditiva":
    st.header("🎯 Análise de Viabilidade por Juiz")
    st.info("Cruza o perfil do Juiz com os Fatos reais do seu cliente.")
    
    try:
        # 1. Puxar Clientes do Banco para não precisar redigitar os fatos
        conn = get_db_connection()
        df_clientes = pd.read_sql("SELECT cliente_nome, historico, tribunal FROM processos", conn)
        conn.close()
        
        if len(df_clientes) > 0:
            col_sel, col_juiz = st.columns(2)
            
            # Seleciona o caso que já existe
            cliente_sel = col_sel.selectbox("Selecione o Caso/Cliente:", df_clientes["cliente_nome"])
            
            # Pega os dados desse cliente automaticamente
            dados_caso = df_clientes[df_clientes["cliente_nome"] == cliente_sel].iloc[0]
            tribunal_auto = dados_caso["tribunal"]
            
            # Tenta extrair o relato do histórico (gambiarra inteligente)
            historico_texto = dados_caso["historico"]
            # Se salvamos como "RELATO_FATOS: ... ||", tentamos limpar
            if "RELATO_FATOS:" in historico_texto:
                fatos_auto = historico_texto.split("RELATO_FATOS:")[1].split("||")[0]
            else:
                fatos_auto = historico_texto # Usa tudo se não achar a tag
            
            # Mostra o resumo para o advogado conferir
            st.caption(f"**Caso Carregado:** {fatos_auto[:150]}...")
            
            # Inputs da Jurimetria
            juiz_nome = col_juiz.text_input("Nome do Juiz(a) que vai julgar:")
            valor_meta = col_juiz.number_input("Quanto queremos ganhar? (R$)", value=5000.0)
            
            if st.button("🔍 Cruzar Dados e Analisar Veredito"):
                if juiz_nome:
                    with st.spinner(f"Simulando julgamento do Dr(a). {juiz_nome} para este caso..."):
                        analise = agente_jurimetria_casada(
                            nome_juiz=juiz_nome, 
                            tribunal=tribunal_auto, 
                            fatos_cliente=fatos_auto, 
                            valor_pedido=valor_meta
                        )
                        st.markdown("---")
                        st.markdown(analise)
                else:
                    st.warning("Digite o nome do Juiz.")
        else:
            st.warning("Cadastre um cliente na Aba 1 primeiro.")
            
    except Exception as e:
        st.error(f"Erro ao buscar dados: {e}")
