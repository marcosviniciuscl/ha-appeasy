"""Geometria: distâncias, rumo e projeção de pontos sobre o traçado da linha."""

import math

R_TERRA = 6371000.0


def haversine(a, b):
    """Distância em metros entre (lat, lon) e (lat, lon)."""
    lat1, lon1 = a
    lat2, lon2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_TERRA * math.asin(min(1.0, math.sqrt(h)))


def bearing(a, b):
    """Rumo em graus de a para b (0 = norte)."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dl = lon2 - lon1
    x = math.sin(dl) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def diferenca_rumo(a, b):
    """Menor diferença absoluta entre dois rumos (0-180)."""
    d = abs((a - b) % 360)
    return min(d, 360 - d)


def metros_por_grau(lat):
    return (111320.0, 111320.0 * max(0.05, math.cos(math.radians(lat))))


def _proj_seg(p, a, b):
    """Projeta o ponto p (lat, lon) no segmento a->b em coordenadas planas locais.
    Devolve (fracao, distancia_metros)."""
    mLat, mLon = metros_por_grau(a[0])
    ax, ay = a[1] * mLon, a[0] * mLat
    bx, by = b[1] * mLon, b[0] * mLat
    px, py = p[1] * mLon, p[0] * mLat
    vx, vy = bx - ax, by - ay
    tam2 = vx * vx + vy * vy
    if tam2 <= 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / tam2))
    cx, cy = ax + t * vx, ay + t * vy
    return t, math.hypot(px - cx, py - cy)


class Rota:
    """Traçado de um itinerário: lista de coordenadas + comprimento acumulado."""

    def __init__(self, pontos):
        # pontos: lista de (lat, lon)
        self.pts = [(float(p[0]), float(p[1])) for p in pontos]
        self.acum = [0.0]
        for i in range(1, len(self.pts)):
            self.acum.append(self.acum[-1] + haversine(self.pts[i - 1], self.pts[i]))
        self.comprimento = self.acum[-1] if self.acum else 0.0

    def __len__(self):
        return len(self.pts)

    def projetar(self, p):
        """Devolve (s, offset): posição no traçado (metros desde o início) e
        distância do ponto ao traçado."""
        if len(self.pts) < 2:
            return 0.0, haversine(p, self.pts[0]) if self.pts else 1e9
        melhor = (0.0, 1e18)
        for i in range(len(self.pts) - 1):
            t, d = _proj_seg(p, self.pts[i], self.pts[i + 1])
            if d < melhor[1]:
                s = self.acum[i] + t * (self.acum[i + 1] - self.acum[i])
                melhor = (s, d)
        return melhor

    def ponto_em(self, s):
        """Coordenada (lat, lon) a s metros do início do traçado."""
        if not self.pts:
            return None
        if s <= 0:
            return self.pts[0]
        if s >= self.comprimento:
            return self.pts[-1]
        lo, hi = 0, len(self.acum) - 1
        while lo < hi - 1:
            meio = (lo + hi) // 2
            if self.acum[meio] <= s:
                lo = meio
            else:
                hi = meio
        trecho = self.acum[hi] - self.acum[lo]
        t = 0.0 if trecho <= 0 else (s - self.acum[lo]) / trecho
        a, b = self.pts[lo], self.pts[hi]
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def distancia_restante(self, s_bus, s_alvo):
        """Quantos metros o ônibus ainda tem que percorrer até o alvo.
        None se o alvo já ficou para trás."""
        if self.comprimento <= 0:
            return None
        d = s_alvo - s_bus
        return d if d > -80 else None

    def fracao(self, s):
        return 0.0 if self.comprimento <= 0 else max(0.0, min(1.0, s / self.comprimento))
