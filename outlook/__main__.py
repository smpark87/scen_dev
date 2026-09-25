"""로컬 전용 실행점. 배포/외부 바인딩을 하지 않는다."""
from waitress import serve

from outlook.app import create_app

if __name__ == "__main__":
    serve(create_app(), host="127.0.0.1", port=8765)
