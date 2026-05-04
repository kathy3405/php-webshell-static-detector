import re

_SUPERGLOBALS = {
    "$_post", "$_get", "$_request", "$_cookie",
    "$_server", "$_files", "$_session",
}
_CALL_PARENTS = {
    "function_call_expression", "member_call_expression",
    "scoped_call_expression",   "object_creation_expression",
}

try:
    from tree_sitter_languages import get_parser as _get_parser
    _PARSER = _get_parser("php")
    _USE_AST = True
except Exception:
    _PARSER  = None
    _USE_AST = False
    print("[warn] tree-sitter PHP parser unavailable — regex fallback active")


class FeatureExtractor:
    """
    Converts PHP source code to a token sequence for TF-IDF.

    Primary:  tree-sitter PHP AST node types.
              Function names → CALL_<name>  (e.g. CALL_eval, CALL_base64_decode)
              Superglobals   → VAR_$_post etc.
    Fallback: regex tokenizer when tree-sitter-languages is not installed.

    To swap the tokenizer, subclass and override `tokenize()`.
    """

    def __init__(self, max_tokens: int = 1_024):
        self.max_tokens = max_tokens
        self.use_ast    = _USE_AST

    def _traverse(self, node, out: list) -> None:
        if node.is_named:
            if node.type == "name" and node.parent and node.parent.type in _CALL_PARENTS:
                txt = node.text.decode("utf-8", errors="replace").lower()
                out.append(f"CALL_{txt}")
            elif node.type == "variable_name":
                txt = node.text.decode("utf-8", errors="replace").lower()
                out.append(f"VAR_{txt}" if txt in _SUPERGLOBALS else "variable_name")
            else:
                out.append(node.type)
        for child in node.children:
            self._traverse(child, out)

    def _ast_tokens(self, code: str) -> list:
        tree = _PARSER.parse(code.encode("utf-8", errors="replace"))
        tokens: list = []
        self._traverse(tree.root_node, tokens)
        return tokens

    def _regex_tokens(self, code: str) -> list:
        code = re.sub(r'/\*.*?\*/', ' ', code, flags=re.DOTALL)
        code = re.sub(r'(//|#)[^\n]*', ' ', code)
        code = re.sub(r'\s+', ' ', code.lower())
        return re.findall(r'\$[a-z_]\w*|[a-z_]\w*|\d+|[(){}\[\];,=<>!&|^~%/*+\-]', code)

    def tokenize(self, code: str) -> list:
        tokens = self._ast_tokens(code) if self.use_ast else self._regex_tokens(code)
        return tokens[:self.max_tokens]

    def to_text(self, code: str) -> str:
        return " ".join(self.tokenize(code))

    def preprocess_dataset(self, samples: list) -> list:
        processed, lengths = [], []
        for s in samples:
            text = self.to_text(s["code"])
            n    = len(text.split())
            lengths.append(n)
            processed.append({"text": text, "label": s["label"]})

        truncated = sum(1 for l in lengths if l >= self.max_tokens)
        print(f"[extract] {len(processed)} samples")
        print(f"          mode={'AST' if self.use_ast else 'regex'} | "
              f"avg={sum(lengths)//len(lengths)} tokens | "
              f"truncated={truncated} ({truncated/len(processed)*100:.1f}%)")
        return processed
