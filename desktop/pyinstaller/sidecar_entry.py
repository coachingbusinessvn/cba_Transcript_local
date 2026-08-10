"""PyInstaller entrypoint for ViTranscript sidecar — chỉ gọi app.server.main()."""
from app.server import main

if __name__ == "__main__":
    main()
