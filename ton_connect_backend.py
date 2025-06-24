from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import uvicorn

app = FastAPI()
sessions = {}  # session_id: address

@app.get("/connect", response_class=HTMLResponse)
async def connect_wallet(tg_id: str):
    session_id = tg_id
    html = f"""
    <html>
    <head>
        <title>TON Connect</title>
        <script src='https://unpkg.com/@tonconnect/ui@latest/dist/tonconnect-ui.min.js'></script>
    </head>
    <body>
        <h2>Подключите TON-кошелек</h2>
        <div id='ton-connect'></div>
        <script>
            const tonConnectUI = new TON_CONNECT_UI.TonConnectUI({{
                manifestUrl: 'http://localhost:8080/tonconnect-manifest.json',
                buttonRootId: 'ton-connect'
            }});
            tonConnectUI.onStatusChange(walletInfo => {{
                if (walletInfo && walletInfo.account) {{
                    fetch('/set_address?session_id={session_id}&address=' + walletInfo.account.address);
                    document.body.innerHTML += '<p>Кошелек подключен: ' + walletInfo.account.address + '</p>';
                }}
            }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/set_address")
async def set_address(session_id: str, address: str):
    sessions[session_id] = address
    return JSONResponse({"ok": True})

@app.get("/get_address")
async def get_address(session_id: str):
    address = sessions.get(session_id)
    return JSONResponse({"address": address})

@app.get("/tonconnect-manifest.json")
async def manifest():
    return FileResponse("tonconnect-manifest.json", media_type="application/json")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080) 