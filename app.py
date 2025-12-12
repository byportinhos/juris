import streamlit as st
import time

# Configuração da página
st.set_page_config(page_title="Sistema Jurídico & Jurimetria", layout="wide")

st.title("⚖️ Assistente de Petições e Jurimetria")

# Barra lateral para navegação
menu = st.sidebar.selectbox("Menu", ["Investigação de Juiz (Jurimetria)", "Gerador de Petições"])

# --- MÓDULO 1: JURIMETRIA ---
if menu == "Investigação de Juiz (Jurimetria)":
    st.header("🕵️ Investigação de Perfil de Magistrado")
    st.info("Conectado à API DataJud (Simulação para MVP)")
    
    col1, col2 = st.columns(2)
    with col1:
        nome_juiz = st.text_input("Nome do Juiz(a)", placeholder="Ex: João da Silva")
    with col2:
        assunto = st.text_input("Assunto Processual", placeholder="Ex: Dano Moral - Atraso Aéreo")
        
    if st.button("Buscar Decisões"):
        if nome_juiz:
            with st.spinner(f"Buscando sentenças de {nome_juiz} na base do CNJ..."):
                time.sleep(2) # Simulando tempo de busca na API
                
                # AQUI ENTRARÁ SUA LÓGICA DO DATAJUD FUTURAMENTE
                # Por enquanto, simulo resultados para você ver a tela funcionando
                st.success("Foram encontradas 15 sentenças recentes!")
                
                st.subheader("📊 Tendência Identificada")
                st.markdown(f"""
                *   **Perfil:** Pró-Consumidor em casos aéreos.
                *   **Média de Condenação:** R$ 5.000,00 a R$ 8.000,00.
                *   **Argumento Vencedor:** Citar "Desvio Produtivo do Consumidor".
                """)
                
                st.subheader("Últimas Decisões Relevantes:")
                st.write(f"1. Proc 00123/2024: Condenou a LATAM em R$ 6.000 ({assunto})")
                st.write(f"2. Proc 00456/2024: Condenou a GOL em R$ 5.000 ({assunto})")
        else:
            st.warning("Digite o nome do juiz.")

# --- MÓDULO 2: GERADOR DE PETIÇÕES ---
elif menu == "Gerador de Petições":
    st.header("📄 Gerador de Minutas com IA")
    
    tipo_peca = st.selectbox("Tipo de Peça", ["Petição Inicial", "Contestação", "Réplica"])
    fato = st.text_area("Descreva os fatos e dados do cliente:")
    
    if st.button("Gerar Minuta"):
        if fato:
            with st.spinner("A Inteligência Artificial está escrevendo..."):
                time.sleep(2)
                st.subheader("Minuta Gerada:")
                
                # Simulando texto gerado
                texto_peticao = f"""EXCELENTÍSSIMO SENHOR DOUTOR JUIZ DE DIREITO...\n\nVem a parte autora, diante dos fatos: {fato}...\nRequer a procedência total."""
                
                st.text_area("Copie o texto abaixo:", value=texto_peticao, height=300)
                st.download_button("Baixar .DOCX", data=texto_peticao, file_name="peticao.txt")
        else:
            st.warning("Descreva os fatos primeiro.")
