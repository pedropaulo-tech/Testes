#!/usr/bin/env python3

from __future__ import annotations

import sys
import json
import subprocess
import threading
import urllib.request
import urllib.error
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

import chess
import chess.pgn
import pygame

# ── Configuração visual ──────────────────────────────────────────────────────
BOARD_SIZE = 640
SQUARE = BOARD_SIZE // 8
PANEL_W = 280
WIDTH = BOARD_SIZE + PANEL_W
HEIGHT = BOARD_SIZE
FPS = 60

COLORS = {
    "light": (240, 217, 181),
    "dark": (181, 136, 99),
    "light_hi": (205, 210, 106),
    "dark_hi": (170, 162, 58),
    "select": (255, 255, 100),
    "legal": (100, 180, 100),
    "legal_cap": (220, 80, 80),
    "check": (224, 60, 60),
    "last": (205, 210, 106),
    "panel_bg": (32, 34, 37),
    "panel_card": (42, 45, 50),
    "text": (230, 230, 230),
    "muted": (150, 155, 160),
    "accent": (129, 182, 76),
    "danger": (220, 80, 80),
    "white_piece": (250, 250, 250),
    "black_piece": (30, 30, 30),
    "outline": (20, 20, 20),
}

UNICODE_PIECES = {
    chess.PAWN: ("♙", "♟"),
    chess.KNIGHT: ("♘", "♞"),
    chess.BISHOP: ("♗", "♝"),
    chess.ROOK: ("♖", "♜"),
    chess.QUEEN: ("♕", "♛"),
    chess.KING: ("♔", "♚"),
}

PIECE_ASSET_NAMES = {
    chess.PAWN: "P",
    chess.KNIGHT: "N",
    chess.BISHOP: "B",
    chess.ROOK: "R",
    chess.QUEEN: "Q",
    chess.KING: "K",
}

PIECE_NAMES = {
    chess.PAWN: "Peão",
    chess.KNIGHT: "Cavalo",
    chess.BISHOP: "Bispo",
    chess.ROOK: "Torre",
    chess.QUEEN: "Dama",
    chess.KING: "Rei",
}

OLLAMA_API = "http://127.0.0.1:11434"


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    action: str
    primary: bool = False


class ChessApp:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Xadrez — regras completas")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()

        # Fontes (fallback se símbolo unicode falhar)
        self.font_piece = self._load_font(52)
        self.font_ui = self._load_font(18)
        self.font_small = self._load_font(14)
        self.font_title = self._load_font(22)
        self.font_promo = self._load_font(40)
        self.piece_images = self._load_piece_images()

        self.board = chess.Board()
        self.flipped = False
        self.selected: Optional[chess.Square] = None
        self.legal_targets: set[chess.Square] = set()
        self.last_move: Optional[chess.Move] = None
        self.move_history: list[chess.Move] = []
        self.redo_stack: list[chess.Move] = []
        self.status = "Brancas jogam"
        self.game_over = False
        self.promoting: Optional[chess.Move] = None  # move parcial aguardando promoção
        self.hover_sq: Optional[chess.Square] = None
        self.ai_enabled = False
        self.ai_color: Optional[chess.Color] = None
        self.ai_model = ""
        self.ai_difficulty = "Equilibrado"
        self.ai_thinking = False
        self.ai_setup = False
        self.ai_setup_option = "brancas"
        self.ai_setup_difficulty = 1
        self.ai_models: list[str] = []
        self.ai_model_index = 0
        self._ai_move_pending = False
        self._load_ai_models()

        self.buttons = self._build_buttons()
        self._update_status()

    def _load_font(self, size: int) -> pygame.font.Font:
        # Tenta fontes com bom suporte a unicode de xadrez
        candidates = [
            "DejaVu Sans",
            "FreeSerif",
            "Segoe UI Symbol",
            "Arial Unicode MS",
            "Noto Sans Symbols",
            "Symbola",
        ]
        for name in candidates:
            path = pygame.font.match_font(name)
            if path:
                try:
                    return pygame.font.Font(path, size)
                except Exception:
                    pass
        return pygame.font.SysFont(None, size)

    def _load_piece_images(self) -> dict[str, pygame.Surface]:
        images: dict[str, pygame.Surface] = {}
        assets_dir = Path(__file__).resolve().parent / "assets" / "pieces"
        for piece_type, asset_name in PIECE_ASSET_NAMES.items():
            for color, prefix in ((chess.WHITE, "w"), (chess.BLACK, "b")):
                key = f"{prefix}_{piece_type}"
                path = assets_dir / f"{prefix}{asset_name}.png"
                try:
                    image = pygame.image.load(str(path)).convert_alpha()
                    images[key] = pygame.transform.smoothscale(
                        image, (SQUARE - 8, SQUARE - 8)
                    )
                except (pygame.error, OSError):
                    pass
        return images

    def _draw_piece(self, piece: chess.Piece, rect: pygame.Rect) -> None:
        prefix = "w" if piece.color == chess.WHITE else "b"
        key = f"{prefix}_{piece.piece_type}"
        image = self.piece_images.get(key)
        if image is not None:
            self.screen.blit(
                image,
                (rect.centerx - image.get_width() // 2,
                 rect.centery - image.get_height() // 2),
            )
            return

        symbol = UNICODE_PIECES[piece.piece_type][0 if piece.color == chess.WHITE else 1]
        text = self.font_piece.render(
            symbol,
            True,
            COLORS["white_piece"] if piece.color == chess.WHITE else COLORS["black_piece"],
        )
        self.screen.blit(
            text,
            (rect.centerx - text.get_width() // 2,
             rect.centery - text.get_height() // 2 + 2),
        )

    def _build_buttons(self) -> list[Button]:
        x = BOARD_SIZE + 20
        y = HEIGHT - 260
        w, h = PANEL_W - 40, 36
        gap = 8
        specs = [
            ("Desfazer", "undo"),
            ("Refazer", "redo"),
            ("Virar tabuleiro", "flip"),
            ("Reiniciar", "reset"),
            ("IA: configurar", "ai"),
        ]
        buttons = []
        for i, (label, action) in enumerate(specs):
            rect = pygame.Rect(x, y + i * (h + gap), w, h)
            buttons.append(Button(rect, label, action, primary=(action == "reset")))
        return buttons

    # ── Coordenadas ──────────────────────────────────────────────────────────
    def sq_to_xy(self, square: chess.Square) -> tuple[int, int]:
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        if self.flipped:
            file = 7 - file
            rank = 7 - rank
        return file * SQUARE, (7 - rank) * SQUARE

    def xy_to_sq(self, x: int, y: int) -> Optional[chess.Square]:
        if x < 0 or y < 0 or x >= BOARD_SIZE or y >= BOARD_SIZE:
            return None
        file = x // SQUARE
        rank = 7 - (y // SQUARE)
        if self.flipped:
            file = 7 - file
            rank = 7 - rank
        return chess.square(file, rank)

    # ── Lógica de jogo ───────────────────────────────────────────────────────
    def select_square(self, square: chess.Square) -> None:
        if self.game_over or self.promoting:
            return

        piece = self.board.piece_at(square)

        # Já tem seleção: tenta mover
        if self.selected is not None:
            if square == self.selected:
                self._clear_selection()
                return
            move = chess.Move(self.selected, square)
            # Promoção: se for peão chegando na última fila
            if self._is_promotion_move(self.selected, square):
                # Guarda o move base e abre seletor
                self.promoting = chess.Move(self.selected, square, promotion=chess.QUEEN)
                self.legal_targets = set()
                return
            # Aceita qualquer promoção legal se já vier com promoção (não neste fluxo)
            if move not in self.board.legal_moves:
                # Tenta capturas / destinos legais sem promoção
                found = None
                for m in self.board.legal_moves:
                    if m.from_square == self.selected and m.to_square == square and not m.promotion:
                        found = m
                        break
                if found is None:
                    # Clica em outra peça própria → troca seleção
                    if piece and piece.color == self.board.turn:
                        self._set_selection(square)
                    else:
                        self._clear_selection()
                    return
                move = found
            self._push_move(move)
            return

        # Nova seleção
        if piece and piece.color == self.board.turn:
            self._set_selection(square)

    def _is_promotion_move(self, fr: chess.Square, to: chess.Square) -> bool:
        piece = self.board.piece_at(fr)
        if not piece or piece.piece_type != chess.PAWN:
            return False
        to_rank = chess.square_rank(to)
        if piece.color == chess.WHITE and to_rank == 7:
            return any(
                m.from_square == fr and m.to_square == to and m.promotion
                for m in self.board.legal_moves
            )
        if piece.color == chess.BLACK and to_rank == 0:
            return any(
                m.from_square == fr and m.to_square == to and m.promotion
                for m in self.board.legal_moves
            )
        return False

    def _set_selection(self, square: chess.Square) -> None:
        self.selected = square
        self.legal_targets = {
            m.to_square for m in self.board.legal_moves if m.from_square == square
        }

    def _clear_selection(self) -> None:
        self.selected = None
        self.legal_targets = set()

    def _push_move(self, move: chess.Move) -> None:
        if move not in self.board.legal_moves:
            # Aceita promoção específica
            if not any(
                m.from_square == move.from_square
                and m.to_square == move.to_square
                and m.promotion == move.promotion
                for m in self.board.legal_moves
            ):
                self._clear_selection()
                return
        self.board.push(move)
        self.move_history.append(move)
        self.redo_stack.clear()
        self.last_move = move
        self._clear_selection()
        self.promoting = None
        self._update_status()
        self._request_ai_move()

    def _load_ai_models(self) -> None:
        try:
            with urllib.request.urlopen(f"{OLLAMA_API}/api/tags", timeout=2) as response:
                data = json.loads(response.read().decode("utf-8"))
            self.ai_models = [model["name"] for model in data.get("models", [])]
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            self._start_portable_ollama()
            self.ai_models = []
        if self.ai_models:
            self.ai_model = self.ai_models[0]

    def _start_portable_ollama(self) -> None:
        candidates = [
            Path.home() / "Downloads" / "Projetos Github-Portifolios" / "ia-local-portatil",
            Path(__file__).resolve().parent.parent / "Projetos Github-Portifolios" / "ia-local-portatil",
        ]
        for project_dir in candidates:
            ollama = project_dir / "bin" / "ollama.exe"
            if not ollama.exists():
                continue
            env = dict(__import__("os").environ)
            env["OLLAMA_MODELS"] = str(project_dir / "modelos")
            env["OLLAMA_HOST"] = "127.0.0.1:11434"
            try:
                subprocess.Popen(
                    [str(ollama), "serve"],
                    cwd=str(project_dir),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError:
                continue
            return

    def _request_ai_move(self) -> None:
        if (
            not self.ai_enabled
            or self.game_over
            or self.board.turn != self.ai_color
            or self.ai_thinking
        ):
            return
        self.ai_thinking = True
        position = self.board.copy(stack=True)
        position_fen = position.fen()
        self.status = "IA está pensando..."
        threading.Thread(
            target=self._calculate_ai_move,
            args=(position, position_fen),
            daemon=True,
        ).start()

    def _calculate_ai_move(
        self,
        position: chess.Board,
        position_fen: str,
    ) -> None:
        move = self._choose_ai_move(position)
        self._ai_move_pending = True
        self._ai_move_result = move
        self._ai_move_fen = position_fen

    def _choose_ai_move(self, position: Optional[chess.Board] = None) -> Optional[chess.Move]:
        position = position or self.board
        legal_moves = list(position.legal_moves)
        if not legal_moves:
            return None

        if not self.ai_model:
            # Sem Ollama disponível: jogada segura local, sem bloquear o jogo.
            return self._fallback_ai_move(position, legal_moves)

        prompt = (
            "Você é um jogador de xadrez. Escolha exatamente um lance legal.\n"
            f"Posição FEN: {position.fen()}\n"
            "Dificuldade: " + self.ai_difficulty + "\n"
            "Lances legais em UCI: "
            + ", ".join(move.uci() for move in legal_moves)
            + "\nResponda somente com o lance UCI, por exemplo: e2e4"
        )
        try:
            payload = json.dumps({
                "model": self.ai_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": [0.9, 0.45, 0.15][self.ai_setup_difficulty],
                    "num_predict": 12,
                },
            }).encode("utf-8")
            request = urllib.request.Request(
                f"{OLLAMA_API}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            answer = data.get("response", "").strip().lower()
            for move in legal_moves:
                if move.uci() in answer:
                    return move
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            pass
        return self._fallback_ai_move(position, legal_moves)

    def _fallback_ai_move(
        self,
        position: chess.Board,
        legal_moves: list[chess.Move],
    ) -> chess.Move:
        import random

        material = {
            chess.PAWN: 100,
            chess.KNIGHT: 320,
            chess.BISHOP: 330,
            chess.ROOK: 500,
            chess.QUEEN: 900,
            chess.KING: 20000,
        }
        scored = []
        for move in legal_moves:
            board_after = position.copy()
            captured_piece = position.piece_at(move.to_square)
            board_after.push(move)
            score = material.get(captured_piece.piece_type, 0) if captured_piece else 0
            if board_after.is_checkmate():
                score += 100000
            elif board_after.is_check():
                score += 100
            scored.append((score, move))
        scored.sort(key=lambda item: item[0], reverse=True)
        pool = scored[: max(1, 3 - self.ai_setup_difficulty)]
        return random.choice(pool)[1]

    def choose_promotion(self, piece_type: chess.PieceType) -> None:
        if not self.promoting:
            return
        move = chess.Move(
            self.promoting.from_square,
            self.promoting.to_square,
            promotion=piece_type,
        )
        self._push_move(move)

    def undo(self) -> None:
        if not self.board.move_stack:
            return
        self._ai_move_pending = False
        self._ai_move_result = None
        self._ai_move_fen = None
        self.ai_thinking = False
        moves_to_undo = 1
        if self.ai_enabled and self.board.turn != self.ai_color:
            moves_to_undo = 2
        for _ in range(moves_to_undo):
            if not self.board.move_stack:
                break
            move = self.board.pop()
            self.redo_stack.append(move)
            if self.move_history:
                self.move_history.pop()
        self.last_move = self.board.peek() if self.board.move_stack else None
        self.game_over = False
        self.promoting = None
        self._clear_selection()
        self._update_status()

    def redo(self) -> None:
        if not self.redo_stack:
            return
        move = self.redo_stack.pop()
        self.board.push(move)
        self.move_history.append(move)
        self.last_move = move
        self._clear_selection()
        self._update_status()
        self._request_ai_move()

    def reset(self) -> None:
        self.board.reset()
        self.move_history.clear()
        self.redo_stack.clear()
        self.last_move = None
        self.game_over = False
        self.promoting = None
        self._clear_selection()
        self._update_status()
        self._request_ai_move()

    def _update_status(self) -> None:
        if self.board.is_checkmate():
            winner = "Pretas" if self.board.turn == chess.WHITE else "Brancas"
            self.status = f"Xeque-mate! {winner} vencem"
            self.game_over = True
        elif self.board.is_stalemate():
            self.status = "Empate por afogamento (stalemate)"
            self.game_over = True
        elif self.board.is_insufficient_material():
            self.status = "Empate por material insuficiente"
            self.game_over = True
        elif self.board.is_seventyfive_moves():
            self.status = "Empate pela regra dos 75 lances"
            self.game_over = True
        elif self.board.is_fivefold_repetition():
            self.status = "Empate por repeticao quintuplicada"
            self.game_over = True
        elif self.board.can_claim_fifty_moves():
            self.status = "Empate possível (regra dos 50 lances)"
            self.game_over = False
        elif self.board.can_claim_threefold_repetition():
            self.status = "Empate possível (repetição tripla)"
            self.game_over = False
        elif self.board.is_check():
            side = "Brancas" if self.board.turn == chess.WHITE else "Pretas"
            self.status = f"Xeque! {side} jogam"
            self.game_over = False
        else:
            side = "Brancas" if self.board.turn == chess.WHITE else "Pretas"
            self.status = f"{side} jogam"
            self.game_over = False

    # ── Desenho ──────────────────────────────────────────────────────────────
    def draw(self) -> None:
        self.screen.fill(COLORS["panel_bg"])
        self._apply_pending_ai_move()
        self._draw_board()
        self._draw_last_move()
        self._draw_check()
        self._draw_selection()
        self._draw_legal()
        self._draw_pieces()
        self._draw_coordinates()
        self._draw_panel()
        if self.promoting:
            self._draw_promotion_ui()
        if self.ai_setup:
            self._draw_ai_setup()
        pygame.display.flip()

    def _apply_pending_ai_move(self) -> None:
        if not getattr(self, "_ai_move_pending", False):
            return
        self._ai_move_pending = False
        move = getattr(self, "_ai_move_result", None)
        move_fen = getattr(self, "_ai_move_fen", None)
        self.ai_thinking = False
        if move_fen is not None and move_fen != self.board.fen():
            return
        if move is not None and move in self.board.legal_moves:
            self._push_move(move)

    def _draw_board(self) -> None:
        for rank in range(8):
            for file in range(8):
                is_light = (file + rank) % 2 == 0
                color = COLORS["light"] if is_light else COLORS["dark"]
                x = file * SQUARE
                y = rank * SQUARE
                pygame.draw.rect(self.screen, color, (x, y, SQUARE, SQUARE))

    def _draw_last_move(self) -> None:
        if not self.last_move:
            return
        for sq in (self.last_move.from_square, self.last_move.to_square):
            x, y = self.sq_to_xy(sq)
            file = chess.square_file(sq)
            rank = chess.square_rank(sq)
            is_light = (file + rank) % 2 == 1 if self.flipped else (file + rank) % 2 == 0
            # Usa destaque independente da cor da casa
            overlay = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
            overlay.fill((205, 210, 106, 140))
            self.screen.blit(overlay, (x, y))

    def _draw_check(self) -> None:
        if not self.board.is_check():
            return
        king_sq = self.board.king(self.board.turn)
        if king_sq is None:
            return
        x, y = self.sq_to_xy(king_sq)
        overlay = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
        overlay.fill((224, 60, 60, 160))
        self.screen.blit(overlay, (x, y))

    def _draw_selection(self) -> None:
        if self.selected is None:
            return
        x, y = self.sq_to_xy(self.selected)
        overlay = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
        overlay.fill((255, 255, 51, 120))
        self.screen.blit(overlay, (x, y))

    def _draw_legal(self) -> None:
        for sq in self.legal_targets:
            x, y = self.sq_to_xy(sq)
            cx, cy = x + SQUARE // 2, y + SQUARE // 2
            target_piece = self.board.piece_at(sq)
            if target_piece:
                # Anel de captura
                pygame.draw.circle(self.screen, COLORS["legal_cap"], (cx, cy), SQUARE // 2 - 4, 5)
            else:
                # Ponto de destino
                pygame.draw.circle(self.screen, (0, 0, 0, 80), (cx, cy), 12)
                s = pygame.Surface((SQUARE, SQUARE), pygame.SRCALPHA)
                pygame.draw.circle(s, (20, 20, 20, 90), (SQUARE // 2, SQUARE // 2), 14)
                self.screen.blit(s, (x, y))

    def _draw_pieces(self) -> None:
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if not piece:
                continue
            x, y = self.sq_to_xy(square)
            self._draw_piece(piece, pygame.Rect(x, y, SQUARE, SQUARE))

    def _draw_coordinates(self) -> None:
        files = "hgfedcba" if self.flipped else "abcdefgh"
        ranks = "12345678" if self.flipped else "87654321"
        for i, ch in enumerate(files):
            color = COLORS["dark"] if i % 2 == 0 else COLORS["light"]
            t = self.font_small.render(ch, True, color)
            self.screen.blit(t, (i * SQUARE + SQUARE - 14, BOARD_SIZE - 16))
        for i, ch in enumerate(ranks):
            color = COLORS["light"] if i % 2 == 0 else COLORS["dark"]
            t = self.font_small.render(ch, True, color)
            self.screen.blit(t, (4, i * SQUARE + 4))

    def _draw_panel(self) -> None:
        # Fundo do painel já está preenchido
        x0 = BOARD_SIZE + 16

        title = self.font_title.render("Xadrez", True, COLORS["text"])
        self.screen.blit(title, (x0, 16))

        # Status
        status_color = COLORS["danger"] if self.game_over or self.board.is_check() else COLORS["accent"]
        # Quebra linha se necessário
        status_lines = self._wrap(self.status, 28)
        sy = 50
        for line in status_lines:
            t = self.font_ui.render(line, True, status_color)
            self.screen.blit(t, (x0, sy))
            sy += 22

        # Turno / indicador
        turn_label = "Brancas" if self.board.turn == chess.WHITE else "Pretas"
        t = self.font_small.render(f"Vez: {turn_label}", True, COLORS["muted"])
        self.screen.blit(t, (x0, sy + 8))

        # Material (simples)
        mat = self._material_diff()
        if mat > 0:
            mat_txt = f"Vantagem brancas: +{mat}"
        elif mat < 0:
            mat_txt = f"Vantagem pretas: +{-mat}"
        else:
            mat_txt = "Material equilibrado"
        t = self.font_small.render(mat_txt, True, COLORS["muted"])
        self.screen.blit(t, (x0, sy + 28))

        # Lista de lances
        hist_y = sy + 56
        t = self.font_ui.render("Lances", True, COLORS["text"])
        self.screen.blit(t, (x0, hist_y))
        hist_y += 26

        # Área scrollável simples — mostra últimos ~12 pares
        sans = self._san_list()
        max_show = 14
        start = max(0, len(sans) - max_show)
        for i, san in enumerate(sans[start:]):
            num = start + i + 1
            line = f"{num}. {san}"
            color = COLORS["text"] if i == len(sans[start:]) - 1 else COLORS["muted"]
            t = self.font_small.render(line, True, color)
            self.screen.blit(t, (x0, hist_y + i * 18))

        # Botões
        for btn in self.buttons:
            bg = COLORS["accent"] if btn.primary else COLORS["panel_card"]
            pygame.draw.rect(self.screen, bg, btn.rect, border_radius=8)
            pygame.draw.rect(self.screen, (60, 64, 70), btn.rect, 1, border_radius=8)
            label = self.font_ui.render(btn.label, True, COLORS["text"])
            lx = btn.rect.centerx - label.get_width() // 2
            ly = btn.rect.centery - label.get_height() // 2
            self.screen.blit(label, (lx, ly))

        # Dica
        tip = self.font_small.render("Clique peça → destino", True, COLORS["muted"])
        self.screen.blit(tip, (x0, HEIGHT - 28))

    def _draw_promotion_ui(self) -> None:
        # Overlay escuro
        overlay = pygame.Surface((BOARD_SIZE, BOARD_SIZE), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        types = [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]
        color = self.board.turn
        box_w = SQUARE * 4 + 40
        box_h = SQUARE + 40
        bx = (BOARD_SIZE - box_w) // 2
        by = (BOARD_SIZE - box_h) // 2
        pygame.draw.rect(self.screen, COLORS["panel_card"], (bx, by, box_w, box_h), border_radius=12)
        pygame.draw.rect(self.screen, COLORS["accent"], (bx, by, box_w, box_h), 2, border_radius=12)

        title = self.font_ui.render("Escolha a promoção", True, COLORS["text"])
        self.screen.blit(title, (bx + 16, by + 8))

        for i, pt in enumerate(types):
            rx = bx + 20 + i * (SQUARE + 4)
            ry = by + 32
            rect = pygame.Rect(rx, ry, SQUARE, SQUARE)
            pygame.draw.rect(self.screen, COLORS["light"], rect, border_radius=6)
            self._draw_piece(chess.Piece(pt, color), rect)
            # Guarda rect em atributo temporário via lista
            if not hasattr(self, "_promo_rects"):
                self._promo_rects = []
        self._promo_rects = [
            (pygame.Rect(bx + 20 + i * (SQUARE + 4), by + 32, SQUARE, SQUARE), pt)
            for i, pt in enumerate(types)
        ]

    def _draw_ai_setup(self) -> None:
        overlay = pygame.Surface((BOARD_SIZE, BOARD_SIZE), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))
        rect = pygame.Rect(100, 155, BOARD_SIZE - 200, 330)
        pygame.draw.rect(self.screen, COLORS["panel_card"], rect, border_radius=12)
        pygame.draw.rect(self.screen, COLORS["accent"], rect, 2, border_radius=12)

        title = self.font_title.render("Configurar adversário IA", True, COLORS["text"])
        self.screen.blit(title, (rect.x + 20, rect.y + 16))

        labels = [
            ("Lado", ["Jogador joga com brancas", "Jogador joga com pretas"]),
            ("Dificuldade", ["Fácil", "Equilibrado", "Difícil"]),
            ("Modelo Ollama", self.ai_models or ["Nenhum modelo disponível"]),
        ]
        self._ai_setup_rects = []
        y = rect.y + 70
        for index, (label, options) in enumerate(labels):
            text = self.font_small.render(label, True, COLORS["muted"])
            self.screen.blit(text, (rect.x + 20, y))
            y += 22
            if index == 2:
                options_width = rect.width - 40
                option_rect = pygame.Rect(rect.x + 20, y, options_width, 34)
                option_index = self.ai_model_index
                option = options[min(option_index, len(options) - 1)]
                selected = True
                pygame.draw.rect(self.screen, COLORS["accent"], option_rect, border_radius=6)
                pygame.draw.rect(self.screen, (70, 74, 80), option_rect, 1, border_radius=6)
                label_text = self.font_small.render(option, True, COLORS["text"])
                self.screen.blit(label_text, (option_rect.x + 10, option_rect.centery - label_text.get_height() // 2))
                self._ai_setup_rects.append((option_rect, index, option_index))
                y += 40
            else:
                gap = 8
                option_width = (rect.width - 40 - gap * (len(options) - 1)) // len(options)
                for option_index, option in enumerate(options):
                    option_rect = pygame.Rect(rect.x + 20 + option_index * (option_width + gap), y, option_width, 34)
                    selected = (
                        (index == 0 and option_index == (0 if self.ai_setup_option == "brancas" else 1))
                        or (index == 1 and option_index == self.ai_setup_difficulty)
                    )
                    pygame.draw.rect(
                        self.screen,
                        COLORS["accent"] if selected else COLORS["panel_card"],
                        option_rect,
                        border_radius=6,
                    )
                    pygame.draw.rect(self.screen, (70, 74, 80), option_rect, 1, border_radius=6)
                    label_text = self.font_small.render(option, True, COLORS["text"])
                    self.screen.blit(
                        label_text,
                        (option_rect.centerx - label_text.get_width() // 2,
                         option_rect.centery - label_text.get_height() // 2),
                    )
                    self._ai_setup_rects.append((option_rect, index, option_index))
                y += 40
            y += 4

        start_rect = pygame.Rect(rect.right - 118, rect.bottom - 48, 98, 34)
        cancel_rect = pygame.Rect(rect.right - 226, rect.bottom - 48, 98, 34)
        pygame.draw.rect(self.screen, COLORS["accent"], start_rect, border_radius=8)
        pygame.draw.rect(self.screen, COLORS["panel_card"], cancel_rect, border_radius=8)
        start_text = self.font_small.render("Iniciar", True, COLORS["outline"])
        cancel_text = self.font_small.render("Cancelar", True, COLORS["text"])
        self.screen.blit(start_text, (start_rect.centerx - start_text.get_width() // 2, start_rect.centery - start_text.get_height() // 2))
        self.screen.blit(cancel_text, (cancel_rect.centerx - cancel_text.get_width() // 2, cancel_rect.centery - cancel_text.get_height() // 2))
        self._ai_setup_start_rect = start_rect
        self._ai_setup_cancel_rect = cancel_rect

    def _wrap(self, text: str, width: int) -> list[str]:
        words = text.split()
        lines: list[str] = []
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            if len(trial) <= width:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [text]

    def _san_list(self) -> list[str]:
        """Gera SAN de todos os lances jogados."""
        tmp = chess.Board()
        result = []
        for move in self.board.move_stack:
            try:
                result.append(tmp.san(move))
            except Exception:
                result.append(move.uci())
            tmp.push(move)
        return result

    def _material_diff(self) -> int:
        values = {
            chess.PAWN: 1,
            chess.KNIGHT: 3,
            chess.BISHOP: 3,
            chess.ROOK: 5,
            chess.QUEEN: 9,
        }
        score = 0
        for pt, val in values.items():
            score += len(self.board.pieces(pt, chess.WHITE)) * val
            score -= len(self.board.pieces(pt, chess.BLACK)) * val
        return score

    # ── Eventos ──────────────────────────────────────────────────────────────
    def handle_click(self, pos: tuple[int, int]) -> None:
        x, y = pos

        if self.ai_setup:
            for rect, section, option_index in getattr(self, "_ai_setup_rects", []):
                if rect.collidepoint(x, y):
                    if section == 0:
                        self.ai_setup_option = "brancas" if option_index == 0 else "pretas"
                    elif section == 1:
                        self.ai_setup_difficulty = option_index
                    elif section == 2:
                        if self.ai_models:
                            self.ai_model_index = (self.ai_model_index + 1) % len(self.ai_models)
                            self.ai_model = self.ai_models[self.ai_model_index]
                    return
            if getattr(self, "_ai_setup_cancel_rect", pygame.Rect(-1, -1, 0, 0)).collidepoint(x, y):
                self.ai_setup = False
                return
            if getattr(self, "_ai_setup_start_rect", pygame.Rect(-1, -1, 0, 0)).collidepoint(x, y):
                self.ai_enabled = True
                self.ai_color = chess.BLACK if self.ai_setup_option == "brancas" else chess.WHITE
                self.ai_difficulty = ["Fácil", "Equilibrado", "Difícil"][self.ai_setup_difficulty]
                self.ai_setup = False
                self.reset()
                return
            return

        # Promoção
        if self.promoting and hasattr(self, "_promo_rects"):
            for rect, pt in self._promo_rects:
                if rect.collidepoint(x, y):
                    self.choose_promotion(pt)
                    return
            return

        # Botões do painel
        for btn in self.buttons:
            if btn.rect.collidepoint(x, y):
                if btn.action == "undo":
                    self.undo()
                elif btn.action == "redo":
                    self.redo()
                elif btn.action == "flip":
                    self.flipped = not self.flipped
                elif btn.action == "reset":
                    self.reset()
                elif btn.action == "ai":
                    self._load_ai_models()
                    self.ai_setup = True
                return

        # Tabuleiro
        if x < BOARD_SIZE:
            sq = self.xy_to_sq(x, y)
            if sq is not None:
                self.select_square(sq)

    def handle_key(self, key: int) -> None:
        if key == pygame.K_ESCAPE:
            self._clear_selection()
            self.promoting = None
        elif key == pygame.K_u or key == pygame.K_LEFT:
            self.undo()
        elif key == pygame.K_r or key == pygame.K_RIGHT:
            self.redo()
        elif key == pygame.K_f:
            self.flipped = not self.flipped
        elif key == pygame.K_n:
            self.reset()
        elif key == pygame.K_p:
            if self.board.is_insufficient_material():
                self.status = "Empate por material insuficiente"
                self.game_over = True
            elif self.board.can_claim_fifty_moves():
                self.status = "Empate pelos 50 lances"
                self.game_over = True
            elif self.board.can_claim_threefold_repetition():
                self.status = "Empate por repeticao tripla"
                self.game_over = True

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    self.handle_key(event.key)

            self.draw()
            self.clock.tick(FPS)

        pygame.quit()


def main() -> None:
    app = ChessApp()
    app.run()


if __name__ == "__main__":
    main()
