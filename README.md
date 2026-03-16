# hyperliquid-operacional

Projeto 100% GitHub gratuito para:
- scanner a cada 5 minutos com GitHub Actions
- alertas no Telegram
- dashboard estático com GitHub Pages
- paper trade simples

## Como usar
1. Crie um repositório público no GitHub
2. Suba estes arquivos
3. Configure os secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
4. Ative GitHub Pages usando a pasta `/web`
5. Rode o workflow `Scanner`

## Rodando localmente
```bash
pip install -r requirements.txt
python src/scanner_github.py
python src/paper_executor.py
python src/build_dashboard_data.py
```
