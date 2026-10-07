import math
import random
import sys
import time
from dataclasses import dataclass, field
from typing import List, Tuple

import pygame

# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────
SCREEN_W = 1200
SCREEN_H = 800
CENTER_X = SCREEN_W // 2
CENTER_Y = SCREEN_H // 2

RING_COUNT = 5
RING_BASE_RADIUS = 80
RING_SPACING = 70
RING_THICKNESS = 12
GAP_ANGLE = math.pi / 9     # 30 degrees

PLAYER_RADIUS = 10
PLAYER_SPEED = 5.0
PLAYER_MAX_STAMINA = 100.0
STAMINA_DRAIN_RATE =2.0
STAMINA_RESTORE_ON_KILL = 22.0
ATTACK_RANGE = 30
ATTACK_DAMAGE = 40
ATTACK_COOLDOWN = 0.4

ENEMY_RADIUS = 9
ENEMY_SPEED = 7.0
ENEMY_HEALTH = 100
ENEMY_DAMAGE = 14.0
ENEMY_ATTACK_COOLDOWN = 0.95

SURVIVE_TIME = 15.0
WIN_CORE_THRESHOLD = RING_BASE_RADIUS - PLAYER_RADIUS - 4

RING_COLORS = [
    (0, 255, 255),
    (0, 200, 255),
    (0, 255, 200),
    (0, 150, 255),
]

CORE_RADIUS = 32
BG_COLOR     = (2, 2, 6)
PLAYER_COLOR = (0, 255, 255)
PLAYER_BDR   = (0, 200, 255)
CORE_COLOR   = (0, 150, 255)
CORE_ACTIVE  = (0, 255, 136)
FPS = 60


# ─────────────────────────────────────────────────────────────────────────────
#  DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Vec2:
    x: float
    y: float

    def dist_to(self, other: 'Vec2') -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def normalize(self) -> 'Vec2':
        mag = math.hypot(self.x, self.y)
        if mag == 0:
            return Vec2(0.0, 0.0)
        return Vec2(self.x / mag, self.y / mag)

    def __add__(self, other: 'Vec2') -> 'Vec2':
        return Vec2(self.x + other.x, self.y + other.y)

    def scale(self, s: float) -> 'Vec2':
        return Vec2(self.x * s, self.y * s)


@dataclass
class Ring:
    index: int
    radius: float
    angle: float
    rotation_speed: float
    color: Tuple[int, int, int]
    gap_angle: float = GAP_ANGLE
    thickness: float = RING_THICKNESS


@dataclass
class Player:
    pos: Vec2
    angle: float = -math.pi / 2
    stamina: float = PLAYER_MAX_STAMINA
    last_attack: float = 0.0
    is_attacking: bool = False
    attack_timer: float = 0.0
    last_repulse: float = 0.0
    history: List[Vec2] = field(default_factory=list)


@dataclass
class Enemy:
    eid: int
    pos: Vec2
    health: float = float(ENEMY_HEALTH)
    max_health: float = float(ENEMY_HEALTH)
    last_attack: float = 0.0
    dying: bool = False
    dying_timer: float = 0.0


@dataclass
class Particle:
    pos: Vec2
    vel: Vec2
    life: float = 1.0
    color: Tuple[int, int, int] = (255, 255, 255)
    radius: float = 3.0


@dataclass
class GameState:
    phase: str = 'menu'
    player: Player = field(default_factory=lambda: Player(
        pos=Vec2(CENTER_X,
                 CENTER_Y + RING_BASE_RADIUS + RING_SPACING * RING_COUNT + 20)
    ))
    rings: List[Ring] = field(default_factory=list)
    enemies: List[Enemy] = field(default_factory=list)
    particles: List[Particle] = field(default_factory=list)
    score: int = 0
    survive_timer: float = 0.0
    in_core: bool = False
    _enemy_counter: int = 0
    _next_spawn: float = 3.0
    _spawn_interval: float = 4.0


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def create_rings() -> List[Ring]:
    rings = []
    for i in range(RING_COUNT):
        radius = RING_BASE_RADIUS + i * RING_SPACING
        speed = (1 if i % 2 == 0 else -1) * (0.20 + i * 0.12)
        rings.append(Ring(
            index=i,
            radius=radius,
            angle=(i * math.pi / 2),
            rotation_speed=speed,
            color=RING_COLORS[i % len(RING_COLORS)],
        ))
    return rings


def fresh_state() -> GameState:
    gs = GameState()
    gs.rings = create_rings()
    return gs


def is_in_gap(ring: Ring, wx: float, wy: float) -> bool:
    angle = math.atan2(wy - CENTER_Y, wx - CENTER_X)
    diff = (angle - ring.angle) % (math.pi * 2)
    if diff > math.pi:
        diff -= math.pi * 2
    return abs(diff) < ring.gap_angle / 2


def ring_collision(ring: Ring, pos: Vec2, radius: float) -> bool:
    d = math.hypot(pos.x - CENTER_X, pos.y - CENTER_Y)
    inner = ring.radius - ring.thickness / 2
    outer = ring.radius + ring.thickness / 2
    if d + radius < inner or d - radius > outer:
        return False
    return not is_in_gap(ring, pos.x, pos.y)


def spawn_particles(gs: GameState, pos: Vec2,
                    color: Tuple[int, int, int], count: int) -> None:
    for _ in range(count):
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(1.0, 4.0)
        gs.particles.append(Particle(
            pos=Vec2(pos.x, pos.y),
            vel=Vec2(math.cos(angle) * speed, math.sin(angle) * speed),
            color=color,
        ))


# ─────────────────────────────────────────────────────────────────────────────
#  GAME UPDATE
# ─────────────────────────────────────────────────────────────────────────────

def update(gs: GameState, dt: float, now: float, keys) -> None:
    if gs.phase != 'playing':
        return

    p = gs.player
    rings = gs.rings

    for ring in rings:
        ring.angle += ring.rotation_speed * dt
    
    dx, dy = 0.0, 0.0
    if keys[pygame.K_LEFT]  or keys[pygame.K_a]: dx -= 1
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]: dx += 1
    if keys[pygame.K_UP]    or keys[pygame.K_w]: dy -= 1
    if keys[pygame.K_DOWN]  or keys[pygame.K_s]: dy += 1

    is_moving = dx != 0 or dy != 0
    is_sprinting = is_moving and (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
    current_speed = PLAYER_SPEED * 1.6 if is_sprinting else PLAYER_SPEED

    if is_moving:
        norm = Vec2(dx, dy).normalize()
        new_pos = Vec2(
            p.pos.x + norm.x * current_speed,
            p.pos.y + norm.y * current_speed,
        )
        p.angle = math.atan2(norm.y, norm.x)
        blocked = any(ring_collision(r, new_pos, PLAYER_RADIUS) for r in rings)
        d_center = math.hypot(new_pos.x - CENTER_X, new_pos.y - CENTER_Y)
        if d_center > RING_BASE_RADIUS + RING_COUNT * RING_SPACING + 60:
            blocked = True
        if not blocked:
            p.pos = new_pos

    p.pos.x = max(PLAYER_RADIUS, min(SCREEN_W - PLAYER_RADIUS, p.pos.x))
    p.pos.y = max(PLAYER_RADIUS, min(SCREEN_H - PLAYER_RADIUS, p.pos.y))

    if is_moving:
        p.history.append(Vec2(p.pos.x, p.pos.y))
        if len(p.history) > 15:
            p.history.pop(0)
    else:
        if len(p.history) > 0:
            p.history.pop(0)

    if p.attack_timer > 0:
        p.attack_timer -= dt
        p.is_attacking = p.attack_timer > 0.2
    else:
        p.is_attacking = False

    if (keys[pygame.K_SPACE] or keys[pygame.K_j]) and \
            now - p.last_attack > ATTACK_COOLDOWN:
        p.last_attack = now
        p.attack_timer = 0.35
        p.is_attacking = True
        for enemy in gs.enemies:
            if enemy.dying:
                continue
            if p.pos.dist_to(enemy.pos) < ATTACK_RANGE + ENEMY_RADIUS:
                enemy.health -= ATTACK_DAMAGE
                spawn_particles(gs, enemy.pos, (255, 153, 51), 5)
                if enemy.health <= 0:
                    enemy.dying = True
                    enemy.dying_timer = 0.4
                    p.stamina = min(PLAYER_MAX_STAMINA,
                                   p.stamina + STAMINA_RESTORE_ON_KILL)
                    
            
                    gs.score += 100
                    spawn_particles(gs, enemy.pos, (255, 200, 50), 14)

    mouse_buttons = pygame.mouse.get_pressed()
    if (keys[pygame.K_k] or mouse_buttons[2]) and p.stamina >= 25 and now - p.last_repulse > 0.5:
        p.last_repulse = now
        p.stamina -= 25
        spawn_particles(gs, p.pos, (0, 255, 255), 40)
        for enemy in gs.enemies:
            if not enemy.dying and p.pos.dist_to(enemy.pos) < 150:
                dir_vec = Vec2(enemy.pos.x - p.pos.x, enemy.pos.y - p.pos.y).normalize()
                enemy.pos.x += dir_vec.x * 80
                enemy.pos.y += dir_vec.y * 80

    current_drain = STAMINA_DRAIN_RATE * 2.5 if is_sprinting else STAMINA_DRAIN_RATE
    p.stamina -= current_drain * dt
    if p.stamina <= 0:
        gs.phase = 'dead'
        return

    d_core = math.hypot(p.pos.x - CENTER_X, p.pos.y - CENTER_Y)
    gs.in_core = d_core < WIN_CORE_THRESHOLD

    if gs.in_core:
        gs.survive_timer += dt
        if gs.survive_timer >= SURVIVE_TIME:
            gs.phase = 'win'
            return
    else:
        gs.survive_timer = max(0.0, gs.survive_timer - dt * 0.5)

    gs._next_spawn -= dt
    if gs._next_spawn <= 0:
        gs._enemy_counter += 1
        angle = random.uniform(0, math.pi * 2)
        outer_r = RING_BASE_RADIUS + (RING_COUNT - 1) * RING_SPACING + RING_SPACING * 0.8
        gs.enemies.append(Enemy(
            eid=gs._enemy_counter,
            pos=Vec2(
                CENTER_X + math.cos(angle) * outer_r,
                CENTER_Y + math.sin(angle) * outer_r,
            ),
        ))
        gs._next_spawn = gs._spawn_interval
        gs._spawn_interval = max(1.5, gs._spawn_interval - 0.1)

    dead_list = []
    for enemy in gs.enemies:
        if enemy.dying:
            enemy.dying_timer -= dt
            if enemy.dying_timer <= 0:
                dead_list.append(enemy)
            continue
        to_p = Vec2(p.pos.x - enemy.pos.x, p.pos.y - enemy.pos.y).normalize()
        try_pos = Vec2(
            enemy.pos.x + to_p.x * ENEMY_SPEED,
            enemy.pos.y + to_p.y * ENEMY_SPEED,
        )
        if not any(ring_collision(r, try_pos, ENEMY_RADIUS) for r in rings):
            enemy.pos = try_pos
        if enemy.pos.dist_to(p.pos) < ENEMY_RADIUS + PLAYER_RADIUS + 2:
            if now - enemy.last_attack > ENEMY_ATTACK_COOLDOWN:
                enemy.last_attack = now
                p.stamina -= ENEMY_DAMAGE
                spawn_particles(gs, p.pos, (255, 50, 50), 4)
                if p.stamina <= 0:
                    gs.phase = 'dead'
                    return
    for e in dead_list:
        gs.enemies.remove(e)

    dead_p = []
    for part in gs.particles:
        part.pos.x += part.vel.x
        part.pos.y += part.vel.y
        part.vel.x *= 0.92
        part.vel.y *= 0.92
        part.life -= dt / 0.8
        if part.life <= 0:
            dead_p.append(part)
    for pp in dead_p:
        gs.particles.remove(pp)
   
        
        






# ─────────────────────────────────────────────────────────────────────────────
#  RENDERER
# ─────────────────────────────────────────────────────────────────────────────

def draw_ring(screen: pygame.Surface, ring: Ring) -> None:
    r = ring.radius
    half = ring.thickness / 2
    gap_half = ring.gap_angle / 2
    start_a = ring.angle + gap_half
    end_a = ring.angle + math.pi * 2 - gap_half
    
    inner_r = r - half - 4
    outer_r = r + half + 4
    
    segments = max(20, int(r / 3))
    span = end_a - start_a
    dt_a = span / segments
    rc, gc, bc = ring.color

    inner_points = []
    outer_points = []
    
    for i in range(segments + 1):
        a = start_a + i * dt_a
        inner_points.append((int(CENTER_X + math.cos(a) * inner_r), int(CENTER_Y + math.sin(a) * inner_r)))
        outer_points.append((int(CENTER_X + math.cos(a) * outer_r), int(CENTER_Y + math.sin(a) * outer_r)))
        
    s = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    color = (rc, gc, bc, 180)
    
    if len(inner_points) > 1:
        pygame.draw.lines(s, color, False, inner_points, 2)
        pygame.draw.lines(s, color, False, outer_points, 2)
        
        for i in range(segments):
            pygame.draw.line(s, color, inner_points[i], outer_points[i+1], 1)
            pygame.draw.line(s, color, outer_points[i], inner_points[i+1], 1)
            
    screen.blit(s, (0, 0))
    
    # Gap marker
    gx = int(CENTER_X + math.cos(ring.angle) * r)
    gy = int(CENTER_Y + math.sin(ring.angle) * r)
    pygame.draw.circle(screen, (0, 255, 255), (gx, gy), 5, 1)
    pygame.draw.line(screen, (0, 255, 255), (gx - 5, gy), (gx + 5, gy), 1)
    pygame.draw.line(screen, (0, 255, 255), (gx, gy - 5), (gx, gy + 5), 1)


def draw_enemy(screen: pygame.Surface, enemy: Enemy) -> None:
    alpha = int(max(0, min(1.0,
        enemy.dying_timer / 0.4 if enemy.dying else 1.0)) * 255)
    ex, ey = int(enemy.pos.x), int(enemy.pos.y)

    e_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    
    rect_w = ENEMY_RADIUS * 2
    rect_h = ENEMY_RADIUS * 2
    
    chip_rect = pygame.Rect(ex - ENEMY_RADIUS, ey - ENEMY_RADIUS, rect_w, rect_h)
    pygame.draw.rect(e_surf, (30, 15, 5, alpha), chip_rect)
    pygame.draw.rect(e_surf, (255, 153, 51, alpha), chip_rect, 1)
    
    for i in range(3):
        px = ex - ENEMY_RADIUS + 3 + i * 6
        if px <= ex + ENEMY_RADIUS:
            pygame.draw.line(e_surf, (255, 153, 51, alpha), (px, ey - ENEMY_RADIUS), (px, ey - ENEMY_RADIUS - 4), 1)
            pygame.draw.line(e_surf, (255, 153, 51, alpha), (px, ey + ENEMY_RADIUS), (px, ey + ENEMY_RADIUS + 4), 1)
        
    screen.blit(e_surf, (0, 0))

    if not enemy.dying and enemy.health < enemy.max_health:
        bw, bh = 22, 3
        bx, by = ex - bw // 2, ey - ENEMY_RADIUS - 8
        pygame.draw.rect(screen, (40, 20, 0), (bx, by, bw, bh))
        fill = int(bw * (enemy.health / enemy.max_health))
        pygame.draw.rect(screen, (255, 153, 51), (bx, by, fill, bh))


def draw_hud(screen: pygame.Surface, gs: GameState, font_sm, font_md) -> None:
    p = gs.player
    hud_x, hud_y = 30, 20

    label = font_sm.render('[ VOLTAGE ]', True, (0, 255, 200))
    screen.blit(label, (hud_x, hud_y))

    bar_x = hud_x
    bar_y = hud_y + label.get_height() + 3
    
    bar_w, bar_h = 190, 12
    pygame.draw.rect(screen, (0, 40, 40), (bar_x, bar_y, bar_w, bar_h))
    pygame.draw.rect(screen, (0, 200, 200), (bar_x, bar_y, bar_w, bar_h), 1)

    pct = max(0.0, p.stamina / PLAYER_MAX_STAMINA)

    fill_col = (0, 255, 255) if pct > 0.5 else (255, 200, 0) if pct > 0.25 else (255, 50, 50)
    
    fill_w = int(bar_w * pct)
    
    if fill_w > 0:
        segments = 20
        seg_w = bar_w / segments
        for i in range(segments):
            sx = bar_x + i * seg_w
            if sx + seg_w - 2 <= bar_x + fill_w:
                pygame.draw.rect(screen, fill_col, (sx + 1, bar_y + 1, seg_w - 2, bar_h - 2))
            else:
                break

    score_txt = f"> SYS_SCORE : {gs.score:06d}"
    score_surf = font_md.render(score_txt, True, (0, 255, 255))
    sx = SCREEN_W - score_surf.get_width() - 30
    sy = 20
    screen.blit(score_surf, (sx, sy))

    if gs.in_core:
        cx = SCREEN_W - 180
        cy = 20 + score_surf.get_height() + 12
        cl = font_sm.render('[ UPLOADING TO CORE ]', True, (0, 255, 136))
        screen.blit(cl, (cx, cy))
        cy2 = cy + cl.get_height() + 3
        pygame.draw.rect(screen, (0, 40, 20), (cx, cy2, 160, 10))
        pygame.draw.rect(screen, (0, 180, 80), (cx, cy2, 160, 10), 1)
        cpct = min(1.0, gs.survive_timer / SURVIVE_TIME)
        if cpct > 0:
            pygame.draw.rect(screen, (0, 255, 136),
                             (cx + 1, cy2 + 1, int(158 * cpct), 8))
        remain = max(0, int(SURVIVE_TIME - gs.survive_timer) + 1)
        rt = font_sm.render(f'T-{remain}s', True, (0, 255, 136))
        screen.blit(rt, (cx, cy2 + 12))

    hint_txt = '> CMD: WASD=Move | SPACE=Execute | K/RClick=Repulse | SHIFT=Overclock | ESC=Term'
    hint = font_sm.render(hint_txt, True, (0, 150, 150))
    screen.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, SCREEN_H - 24))


def draw_game(screen: pygame.Surface, gs: GameState,
              font_sm, font_md, font_lg, font_xl) -> None:
    screen.fill(BG_COLOR)

    grid_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    for gx in range(0, SCREEN_W, 40):
        pygame.draw.line(grid_surf, (0, 50, 100, 40), (gx, 0), (gx, SCREEN_H), 1)
    for gy in range(0, SCREEN_H, 40):
        pygame.draw.line(grid_surf, (0, 50, 100, 40), (0, gy), (SCREEN_W, gy), 1)
    screen.blit(grid_surf, (0, 0))

    p = gs.player
    core_color = CORE_ACTIVE if gs.in_core else CORE_COLOR

    glow_surf = pygame.Surface((CORE_RADIUS * 6, CORE_RADIUS * 6), pygame.SRCALPHA)
    glow_alpha = 55 if gs.in_core else 30
    glow_col = (0, 255, 136, glow_alpha) if gs.in_core else (0, 150, 255, glow_alpha)
    pygame.draw.circle(glow_surf, glow_col,
                       (CORE_RADIUS * 3, CORE_RADIUS * 3), CORE_RADIUS * 3)
    screen.blit(glow_surf, (CENTER_X - CORE_RADIUS * 3, CENTER_Y - CORE_RADIUS * 3))

    core_fill = pygame.Surface((CORE_RADIUS * 2 + 4, CORE_RADIUS * 2 + 4), pygame.SRCALPHA)
    cf_col = (0, 255, 136, 30) if gs.in_core else (0, 150, 255, 20)
    pygame.draw.rect(core_fill, cf_col, (2, 2, CORE_RADIUS * 2, CORE_RADIUS * 2))
    screen.blit(core_fill, (CENTER_X - CORE_RADIUS - 2, CENTER_Y - CORE_RADIUS - 2))

    pygame.draw.rect(screen, core_color, (CENTER_X - CORE_RADIUS, CENTER_Y - CORE_RADIUS, CORE_RADIUS * 2, CORE_RADIUS * 2), 2)
    pygame.draw.circle(screen, core_color, (CENTER_X, CENTER_Y), CORE_RADIUS - 8, 1)
    lbl = font_sm.render('MAIN', True, core_color)
    screen.blit(lbl, (CENTER_X - lbl.get_width() // 2,
                      CENTER_Y - lbl.get_height() // 2 - 8))
    lbl2 = font_sm.render('SYS', True, core_color)
    screen.blit(lbl2, (CENTER_X - lbl2.get_width() // 2,
                       CENTER_Y - lbl2.get_height() // 2 + 8))

    if gs.in_core and gs.survive_timer > 0:
        arc_r = CORE_RADIUS + 12
        arc_rect = pygame.Rect(CENTER_X - arc_r, CENTER_Y - arc_r,
                               arc_r * 2, arc_r * 2)
        progress = gs.survive_timer / SURVIVE_TIME
        start_a = -math.pi / 2
        end_a = start_a + progress * math.pi * 2
        pygame.draw.arc(screen, (0, 255, 136), arc_rect, start_a, end_a, 4)

    for ring in gs.rings:
        draw_ring(screen, ring)

    p_surf = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    
    if len(p.history) > 1:
        points = [(int(pt.x), int(pt.y)) for pt in p.history]
        pygame.draw.lines(p_surf, (0, 255, 255, 100), False, points, 3)

    for part in gs.particles:
        a = int(max(0, min(255, part.life * 255)))
        r = max(1, int(part.radius * part.life))
        pygame.draw.rect(p_surf, (*part.color, a),
                         (int(part.pos.x - r/2), int(part.pos.y - r/2), r, r))
    screen.blit(p_surf, (0, 0))

    for enemy in gs.enemies:
        draw_enemy(screen, enemy)

    if p.is_attacking:
        aura = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        pygame.draw.circle(aura, (0, 255, 255, 28),
                           (int(p.pos.x), int(p.pos.y)),
                           ATTACK_RANGE + ENEMY_RADIUS)
        pygame.draw.circle(aura, (0, 255, 255, 120),
                           (int(p.pos.x), int(p.pos.y)),
                           ATTACK_RANGE + ENEMY_RADIUS, 1)
        screen.blit(aura, (0, 0))

    pg_surf = pygame.Surface((60, 60), pygame.SRCALPHA)
    pygame.draw.rect(pg_surf, (0, 255, 255, 20), (2, 2, 56, 56))
    screen.blit(pg_surf, (int(p.pos.x) - 30, int(p.pos.y) - 30))

    px, py = int(p.pos.x), int(p.pos.y)
    pygame.draw.rect(screen, (0, 50, 50), (px - PLAYER_RADIUS, py - PLAYER_RADIUS, PLAYER_RADIUS * 2, PLAYER_RADIUS * 2))
    pygame.draw.rect(screen, PLAYER_COLOR, (px - PLAYER_RADIUS, py - PLAYER_RADIUS, PLAYER_RADIUS * 2, PLAYER_RADIUS * 2), 2)
    pygame.draw.circle(screen, PLAYER_COLOR, (px, py), 3)

    ex = int(p.pos.x + math.cos(p.angle) * (PLAYER_RADIUS + 7))
    ey = int(p.pos.y + math.sin(p.angle) * (PLAYER_RADIUS + 7))
    pygame.draw.line(screen, (0, 255, 255), (px, py), (ex, ey), 2)

    draw_hud(screen, gs, font_sm, font_md)


# ─────────────────────────────────────────────────────────────────────────────
#  OVERLAY SCREENS
# ─────────────────────────────────────────────────────────────────────────────

def panel(screen: pygame.Surface, rect, border_color) -> None:
    x, y, w, h = rect
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    s.fill((2, 2, 8, 240))
    screen.blit(s, (x, y))
    pygame.draw.rect(screen, border_color, rect, 2)
    ml = 10
    pygame.draw.line(screen, border_color, (x, y), (x + ml, y), 2)
    pygame.draw.line(screen, border_color, (x, y), (x, y + ml), 2)


def draw_menu(screen: pygame.Surface, font_sm, font_md, font_lg, font_xl) -> None:
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))

    pw, ph = 500, 420
    px = (SCREEN_W - pw) // 2
    py = (SCREEN_H - ph) // 2
    panel(screen, (px, py, pw, ph), (0, 255, 255))

    title = font_xl.render('> CHAKRAVYUH_OS', True, (0, 255, 255))
    screen.blit(title, (SCREEN_W // 2 - title.get_width() // 2, py + 28))

    for i, line in enumerate([
        'Bypass the rotating firewall structures.',
        'Upload to the Main Sys for 15s to win.',
    ]):
        s = font_sm.render(line, True, (0, 200, 200))
        screen.blit(s, (SCREEN_W // 2 - s.get_width() // 2, py + 100 + i * 22))

    controls = [
        ('WASD/Arrows',   ': Move CPU Node'),
        ('Space/J',       ': Execute Attack'),
        ('K/R-Click',     ': Repulse Surge (-25V)'),
        ('Voltage',       ': Drains over time; reap processes to restore'),
        ('Goal',          ': Override Main Sys (15s upload)'),
        ('R/ESC',         ': Reboot / Terminate'),
        ('SHIFT',         ': Overclock Speed')
    ]
    cy = py + 158
    for key, desc in controls:
        k = font_sm.render(f"[{key}]", True, (0, 255, 255))
        d = font_sm.render(desc, True, (0, 150, 150))
        screen.blit(k, (px + 30, cy))
        screen.blit(d, (px + 30 + k.get_width() + 8, cy))
        cy += 24

    press = font_md.render('>> Press ENTER to Initialize <<', True, (0, 255, 136))
    screen.blit(press, (SCREEN_W // 2 - press.get_width() // 2, py + ph - 52))


def draw_dead(screen: pygame.Surface, score: int,
              font_sm, font_md, font_lg) -> None:
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))

    pw, ph = 400, 240
    px = (SCREEN_W - pw) // 2
    py = (SCREEN_H - ph) // 2
    panel(screen, (px, py, pw, ph), (255, 50, 50))

    t = font_lg.render('SYS_FAILURE', True, (255, 50, 50))
    screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, py + 30))

    sub = font_sm.render('Node destroyed by firewall.', True, (255, 150, 150))
    screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, py + 98))

    sc = font_md.render(f'Final Score: {score:06d}', True, (0, 255, 255))
    screen.blit(sc, (SCREEN_W // 2 - sc.get_width() // 2, py + 134))

    r = font_sm.render('Press R to Reboot  |  ESC to Terminate', True, (150, 150, 150))
    screen.blit(r, (SCREEN_W // 2 - r.get_width() // 2, py + ph - 44))


def draw_win(screen: pygame.Surface, score: int,
             font_sm, font_md, font_lg) -> None:
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    screen.blit(overlay, (0, 0))

    pw, ph = 420, 250
    px = (SCREEN_W - pw) // 2
    py = (SCREEN_H - ph) // 2
    panel(screen, (px, py, pw, ph), (0, 255, 136))

    t = font_lg.render('OVERRIDE_SUCCESS', True, (0, 255, 136))
    screen.blit(t, (SCREEN_W // 2 - t.get_width() // 2, py + 30))

    sub = font_sm.render('Main Sys hijacked successfully.', True, (0, 200, 100))
    screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, py + 102))

    sc = font_md.render(f'Final Score: {score:06d}', True, (0, 255, 255))
    screen.blit(sc, (SCREEN_W // 2 - sc.get_width() // 2, py + 140))

    r = font_sm.render('Press R to Play Again  |  ESC to Terminate', True, (150, 150, 150))
    screen.blit(r, (SCREEN_W // 2 - r.get_width() // 2, py + ph - 44))


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    pygame.init()
    pygame.display.set_caption('Chakravyuh — Survival Maze')
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()

    font_sm = pygame.font.SysFont('Courier New', 12, bold=True)
    font_md = pygame.font.SysFont('Courier New', 16, bold=True)
    font_lg = pygame.font.SysFont('Courier New', 38, bold=True)
    font_xl = pygame.font.SysFont('Courier New', 52, bold=True)

    gs = fresh_state()

    while True:
        dt = clock.tick(FPS) / 1000.0
        now = time.perf_counter()
        keys = pygame.key.get_pressed()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_RETURN and gs.phase == 'menu':
                    gs = fresh_state()
                    gs.phase = 'playing'
                if event.key == pygame.K_r and gs.phase in ('dead', 'win'):
                    gs = fresh_state()
                    gs.phase = 'playing'

        update(gs, dt, now, keys)

        draw_game(screen, gs, font_sm, font_md, font_lg, font_xl)
        if gs.phase == 'menu':
            draw_menu(screen, font_sm, font_md, font_lg, font_xl)
        elif gs.phase == 'dead':
            draw_dead(screen, gs.score, font_sm, font_md, font_lg)
        elif gs.phase == 'win':
            draw_win(screen, gs.score, font_sm, font_md, font_lg)

        pygame.display.flip()


if __name__ == '__main__':
    main()