from configparser import ConfigParser
from pathlib import Path
from typing import List, Optional

class Settings:
    def __init__(self, config_path: Path):
        parser = ConfigParser()
        with open(config_path, "r", encoding="utf-8") as f:
            parser.read_file(f)

        gen = parser["general"]
        self.output_dir: Path = Path(gen.get("output_dir", "data")).resolve()
        self.concurrency: int = gen.getint("concurrency", fallback=8)
        self.timeout: int = gen.getint("timeout", fallback=20)
        self.max_retries: int = gen.getint("max_retries", fallback=3)
        self.respect_robots: bool = gen.getboolean("respect_robots", fallback=True)
        ua = gen.get("user_agent", fallback="").strip()
        self.user_agent: Optional[str] = ua if ua else None

        urls_raw = parser["targets"].get("urls", "")
        # Split by newline, comma, or semicolon; strip blanks.
        urls: List[str] = []
        for line in urls_raw.splitlines():
            parts = [p.strip() for p in line.split(",") if p.strip()]
            urls.extend(parts)
        self.urls: List[str] = urls

        self.output_dir.mkdir(parents=True, exist_ok=True)
