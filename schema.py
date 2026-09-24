"""
Structures de données d'entrée/sortie du moteur — Osmoz Animae.

Objectif : que ces structures collent le plus possible aux champs du
Google Form de pré-tournée (voir pre-tournee-templates.md dans le projet),
pour que le futur pont formulaire -> moteur n'ait quasiment pas de
traduction à faire.
"""

from __future__ import annotations


from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class WindowType(str, Enum):
    """Correspond à la question 6 du formulaire :
    "Avez-vous une contrainte d'horaire ferme, ou juste une préférence ?"
    """

    NONE = "none"      # aucune contrainte -> libre sur toute la fenêtre du jour
    FLOOR = "floor"     # préférence type "pas avant 16h" -> plancher, pas de plafond
    HARD = "hard"       # contrainte ferme type "seulement l'après-midi" -> fenêtre stricte


@dataclass
class StopWindow:
    type: WindowType = WindowType.NONE
    start_min: Optional[int] = None  # minutes depuis minuit
    end_min: Optional[int] = None    # minutes depuis minuit (ignoré si FLOOR)

    def resolve(self, day_start: int, day_end: int) -> tuple[int, int]:
        """Renvoie la fenêtre effective (lo, hi) à donner au solveur,
        en complétant avec les bornes de la journée quand nécessaire."""
        if self.type == WindowType.NONE:
            return day_start, day_end
        if self.type == WindowType.FLOOR:
            lo = self.start_min if self.start_min is not None else day_start
            return lo, day_end
        if self.type == WindowType.HARD:
            lo = self.start_min if self.start_min is not None else day_start
            hi = self.end_min if self.end_min is not None else day_end
            return lo, hi
        raise ValueError(f"Type de fenêtre inconnu : {self.type}")


@dataclass
class Stop:
    """Un arrêt = un client (un ou plusieurs animaux) à un endroit donné.
    Correspond à une ligne de réponse au formulaire.

    allowed_days : les jours possibles pour ce client (question 5 du
    formulaire — cases cochées). Une liste à un seul élément = jour déjà
    fixé (cas d'usage de solve_day/solve_multi_day, un ordre à calculer
    sur un jour déjà décidé). Plusieurs éléments = jour encore à décider
    par le moteur (cas d'usage de solve_week/solve_week_balanced, qui
    choisissent eux-mêmes lequel des jours possibles utiliser)."""

    id: str                      # identifiant unique, ex. "caroline_landerneau"
    label: str                   # nom affiché, ex. "Caroline Picard (Landerneau)"
    service_minutes: int         # durée totale de la visite (tous animaux compris)
    allowed_days: list[int]      # jour(s) possible(s) ; voir docstring ci-dessus
    window: StopWindow = field(default_factory=StopWindow)
    animals: str = ""            # texte libre, ex. "2 chevaux, 1 chien" (question 4)
    phone: str = ""
    notes: str = ""              # remarques complémentaires (question 8)
    address: str = ""            # adresse géocodable (question 3, "Lieu du rendez-vous"),
                                  # séparée de label : label = affichage humain ("Nom (Lieu)"),
                                  # address = ce qu'on envoie tel quel au géocodeur (ors_client.py).
                                  # Toujours préférer une adresse précise à un simple nom de commune
                                  # (leçon du 24 sept. 2026 : écart de plusieurs minutes sinon).
    client_name: str = ""        # nom du client seul (question 1), séparé de label et address.
                                  # Existe car label combine les deux dans un ordre qui a changé
                                  # entre le prototype ("Lieu (Client)") et form_import.py
                                  # ("Client (Lieu)") -- reconstruire le nom/lieu séparés à partir
                                  # du texte affiché est fragile (bug trouvé le 24 sept. 2026 :
                                  # message WhatsApp inversé, nom et lieu échangés). Toujours
                                  # utiliser client_name/address directement en aval, jamais
                                  # re-parser label.
    abonnement_annuel: bool = False  # case cochée au formulaire (demande de Margaux, 24 sept. 2026) --
                                  # protège ce client d'être celui qu'on écarte en cas de tournée trop
                                  # chargée pour tout le monde (voir weekly.py, PRIORITY_PENALTY) ;
                                  # allowed_days reste par ailleurs la seule contrainte dure sur le
                                  # jour, cochée ou non -- ceci ne fait jamais sortir un client d'un
                                  # jour qu'il n'a pas coché.
                                  # Rempli automatiquement par form_import.py (parse_abonnement) à
                                  # partir de la question "Abonnement annuel ?" du formulaire -- une
                                  # réponse absente ou non reconnue vaut "non abonné" (jamais deviné
                                  # à tort, même principe que le reste de form_import.py).


@dataclass
class DayPlan:
    """Une journée de tournée : ses arrêts, son point de départ, si elle se
    termine par une nuitée sur place (route ouverte) ou un retour au dépôt."""

    day_index: int
    label: str                    # ex. "Mardi 20 octobre"
    start_id: str                 # id du point de départ (dépôt, ou lieu de la nuit précédente)
    end_id: Optional[str] = None  # id du point de retour si route fermée ; None si nuit sur place
    open_route: bool = False      # True = pas de retour, nuit sur place au dernier arrêt résolu
    day_start_min: int = 6 * 60   # 6h00 par défaut
    day_end_min: int = 20 * 60 + 30  # 20h30 par défaut (cadre habituel Osmoz Animae)
    # Fenêtre propre au départ du dépôt (ex. "doit partir entre 6h et 10h").
    # Type NONE (défaut) -> le départ peut avoir lieu n'importe quand dans le jour.
    start_window: StopWindow = field(default_factory=StopWindow)
    # Fenêtre propre au retour, uniquement pertinente si open_route=False.
    # Type NONE (défaut) -> pas de contrainte ajoutée sur l'heure de retour.
    end_window: StopWindow = field(default_factory=StopWindow)


@dataclass
class RouteStep:
    stop_id: str
    label: str
    arrival_min: int
    service_minutes: int

    @property
    def departure_min(self) -> int:
        return self.arrival_min + self.service_minutes


@dataclass
class DayResult:
    day_index: int
    label: str
    steps: list[RouteStep]
    finish_min: int
    feasible: bool
    error: Optional[str] = None
    span_min: Optional[int] = None  # étalement réel (fin - début), utile pour l'équilibrage


@dataclass
class DayConfig:
    """Bornes d'une journée pour l'affectation automatique (solve_week /
    solve_week_balanced) : pas de start_id/end_id explicite comme DayPlan
    (ces jours partent tous du dépôt et y reviennent par défaut — voir
    weekly.py, décision de Margaux du 24 sept. 2026 sur les nuitées)."""

    day_index: int
    label: str
    day_start_min: int = 6 * 60
    day_end_min: int = 20 * 60 + 30
    max_span_min: Optional[int] = None  # plafond dur d'heures cumulées (le "rythme")


@dataclass
class WeekResult:
    day_results: dict[int, DayResult]
    missing_client_ids: list[str]  # clients qu'aucun jour possible n'a pu caser

    @property
    def feasible(self) -> bool:
        return not self.missing_client_ids
