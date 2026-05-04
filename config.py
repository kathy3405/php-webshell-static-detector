from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).parent   # project folder, not CWD


@dataclass
class Config:
    # Paths — always relative to project root
    dataset_dir: Path = field(default_factory=lambda: _ROOT / "dataset")
    raw_dir:     Path = field(default_factory=lambda: _ROOT / "dataset" / "raw")
    log_file:    Path = field(default_factory=lambda: _ROOT / "logs.txt")

    # Collection
    min_len:      int   = 20
    max_len:      int   = 100_000
    benign_ratio: float = 3.0
    max_benign:   int   = 5_000

    # Features
    max_tokens:   int = 1_024
    max_features: int = 10_000

    # Split
    seed:       int   = 42
    test_ratio: float = 0.10
    val_ratio:  float = 0.10

    # Shared training
    epochs:     int   = 10
    batch_size: int   = 32
    lr:         float = 1e-3
    n_folds:    int   = 5

    # TextCNN
    textcnn_embed_dim:    int   = 128
    textcnn_num_filters:  int   = 128
    textcnn_kernel_sizes: tuple = (2, 3, 4)
    textcnn_max_vocab:    int   = 10_000

    # CodeBERT
    enable_codebert:     bool  = True
    codebert_model:      str   = "microsoft/codebert-base"
    codebert_max_len:    int   = 256
    codebert_epochs:     int   = 3
    codebert_batch_size: int   = 16
    codebert_lr:         float = 2e-5

    # Data sources
    webshell_repos: list = field(default_factory=lambda: [
        ("https://github.com/tennc/webshell.git",                       "webshell_tennc"),
        ("https://github.com/xl7dev/WebShell.git",                      "webshell_xl7"),
        ("https://github.com/BlackArch/webshells.git",                  "webshell_blackarch"),
        ("https://github.com/WhiteWinterWolf/wwwolf-php-webshell.git",  "webshell_wwwolf"),
        ("https://github.com/b374k/b374k.git",                          "webshell_b374k"),
        ("https://github.com/fuzzdb-project/fuzzdb.git",                "webshell_fuzzdb"),
    ])

    # Cyc1e183 — 2917 cleaned webshells from 17 sources, stored as zip (may be LFS)
    # https://github.com/Cyc1e183/PHP-Webshell-Dataset
    cyc1e183_zip_url: str = (
        "https://github.com/Cyc1e183/PHP-Webshell-Dataset/raw/master/PHP-Webshell.zip"
    )

    # FWOID dataset (Zenodo — 5001 webshells + 5936 benign, zip password = "123")
    # Paper: NDSS 2025 poster, arXiv:2502.19257
    fwoid_zenodo_record: str   = "14938302"
    fwoid_zip_password:  bytes = b"123"
    enable_fwoid:        bool  = True

    # weevely3 — generates obfuscated PHP backdoors dynamically
    # Requires: pip install weevely3  OR  clone + pip install -r requirements.txt
    enable_weevely:    bool = False
    weevely_n_shells:  int  = 100   # number of shells to generate

    # MWF dataset — requires manual download (Elsevier access needed)
    # DOI: https://doi.org/10.1016/j.cose.2023.103140
    # Set mwf_dir to the extracted dataset folder after manual download
    enable_mwf: bool = False
    mwf_dir:    Path = field(default_factory=lambda: Path(""))

    benign_repos: list = field(default_factory=lambda: [
        ("https://github.com/guzzlehttp/guzzle.git",   "benign_guzzle"),
        ("https://github.com/PHPMailer/PHPMailer.git", "benign_phpmailer"),
        ("https://github.com/Seldaek/monolog.git",     "benign_monolog"),
        ("https://github.com/nikic/PHP-Parser.git",    "benign_phpparser"),
        ("https://github.com/bcit-ci/CodeIgniter.git", "benign_codeigniter"),
        ("https://github.com/vlucas/phpdotenv.git",    "benign_dotenv"),
        ("https://github.com/laravel/laravel.git",     "benign_laravel"),
        ("https://github.com/symfony/demo.git",        "benign_symfony_demo"),
    ])

    def __post_init__(self):
        d = self.dataset_dir
        self.dataset_raw        = d / "dataset_raw.json"
        self.dataset_clean      = d / "dataset_clean.json"
        self.dataset_processed  = d / "dataset_processed.json"
        self.dataset_obfuscated = d / "dataset_obfuscated.json"
        self.split_meta         = d / "split_meta.json"
        self.model_file         = d / "model.pt"
        self.tfidf_file         = d / "tfidf.pkl"
        self.results_file       = d / "results.json"
