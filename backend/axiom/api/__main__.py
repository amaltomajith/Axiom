import os

import uvicorn

if __name__ == "__main__":
    # Local default is loopback only. Containers (Cloud Run, Docker) set HOST=0.0.0.0 and PORT.
    uvicorn.run(
        "axiom.api.app:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=bool(os.environ.get("PORT")),
        forwarded_allow_ips="*" if os.environ.get("PORT") else None,
        reload=False,
    )
