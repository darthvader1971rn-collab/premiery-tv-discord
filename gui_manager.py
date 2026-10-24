import json
import os
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import requests

CONFIG_FILE = "config.json"
TRACKED_FILE = "tracked_shows.json"


def load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class TVTrackerGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Radar Premier TV & VOD - Menedżer Bazy")
        self.root.geometry("1100x650")
        self.root.minsize(900, 500)

        self.config = load_json(CONFIG_FILE, {})
        self.api_key = self.config.get("tmdb_api_key", "").strip()

        self.setup_ui()
        self.refresh_tracked_list()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Zakładka 1: Wyszukiwarka i dodawanie
        self.tab_search = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_search, text="🔍 Szukaj i dodaj do bazy")

        # Zakładka 2: Lista śledzonych
        self.tab_tracked = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_tracked, text="📋 Obserwowane seriale")

        self.setup_search_tab()
        self.setup_tracked_tab()

    def setup_search_tab(self):
        # Panel wyszukiwania
        search_frame = ttk.Frame(self.tab_search, padding=10)
        search_frame.pack(fill="x")

        ttk.Label(
            search_frame, text="Nazwa serialu:", font=("Segoe UI", 10, "bold")
        ).pack(side="left", padx=(0, 5))
        self.search_entry = ttk.Entry(search_frame, font=("Segoe UI", 10))
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self.start_search())

        self.search_btn = ttk.Button(
            search_frame, text="Szukaj w TMDB", command=self.start_search
        )
        self.search_btn.pack(side="left", padx=5)

        self.status_label = ttk.Label(
            self.tab_search, text="Wpisz tytuł i wciśnij Enter.", foreground="gray"
        )
        self.status_label.pack(anchor="w", padx=15, pady=(0, 5))

        # Tabela wyników
        columns = (
            "id",
            "title",
            "orig_title",
            "year",
            "network",
            "vod_pl",
            "next_air",
        )
        self.tree_results = ttk.Treeview(
            self.tab_search,
            columns=columns,
            show="headings",
            selectmode="extended",
        )

        self.tree_results.heading("id", text="ID TMDB")
        self.tree_results.heading("title", text="Tytuł PL")
        self.tree_results.heading("orig_title", text="Tytuł oryginalny")
        self.tree_results.heading("year", text="Rok")
        self.tree_results.heading("network", text="Stacja macierzysta")
        self.tree_results.heading("vod_pl", text="Dostępność VOD (Polska)")
        self.tree_results.heading("next_air", text="Najbliższa emisja")

        self.tree_results.column("id", width=70, anchor="center")
        self.tree_results.column("title", width=180)
        self.tree_results.column("orig_title", width=180)
        self.tree_results.column("year", width=60, anchor="center")
        self.tree_results.column("network", width=130)
        self.tree_results.column("vod_pl", width=180)
        self.tree_results.column("next_air", width=140, anchor="center")

        scroll_y = ttk.Scrollbar(
            self.tab_search,
            orient="vertical",
            command=self.tree_results.yview,
        )
        self.tree_results.configure(yscrollcommand=scroll_y.set)

        self.tree_results.pack(
            side="top", fill="both", expand=True, padx=10, pady=5
        )
        scroll_y.pack(side="right", fill="y", before=self.tree_results)

        # Dolny pasek z akcją
        bottom_frame = ttk.Frame(self.tab_search, padding=10)
        bottom_frame.pack(fill="x")

        ttk.Button(
            bottom_frame,
            text="➕ Dodaj zaznaczone do bazy",
            command=self.add_selected_to_tracked,
        ).pack(side="right", padx=5)

    def setup_tracked_tab(self):
        # Tabela śledzonych pozycji
        columns = ("id", "title", "network", "added_at")
        self.tree_tracked = ttk.Treeview(
            self.tab_tracked,
            columns=columns,
            show="headings",
            selectmode="extended",
        )

        self.tree_tracked.heading("id", text="ID TMDB")
        self.tree_tracked.heading("title", text="Tytuł serialu")
        self.tree_tracked.heading("network", text="Główna stacja / VOD")
        self.tree_tracked.heading("added_at", text="Data dodania")

        self.tree_tracked.column("id", width=90, anchor="center")
        self.tree_tracked.column("title", width=350)
        self.tree_tracked.column("network", width=200)
        self.tree_tracked.column("added_at", width=150, anchor="center")

        scroll_y = ttk.Scrollbar(
            self.tab_tracked,
            orient="vertical",
            command=self.tree_tracked.yview,
        )
        self.tree_tracked.configure(yscrollcommand=scroll_y.set)

        self.tree_tracked.pack(
            side="top", fill="both", expand=True, padx=10, pady=10
        )
        scroll_y.pack(side="right", fill="y", before=self.tree_tracked)

        # Pasek akcji
        btn_frame = ttk.Frame(self.tab_tracked, padding=10)
        btn_frame.pack(fill="x")

        ttk.Button(
            btn_frame,
            text="❌ Usuń zaznaczone z bazy",
            command=self.remove_selected_from_tracked,
        ).pack(side="right", padx=5)
        ttk.Button(
            btn_frame,
            text="🔄 Odśwież listę",
            command=self.refresh_tracked_list,
        ).pack(side="left", padx=5)

    def start_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        if not self.api_key:
            messagebox.showerror(
                "Błąd", "Brak klucza TMDB API w pliku config.json!"
            )
            return

        self.search_btn.config(state="disabled")
        self.status_label.config(
            text="Przeszukiwanie bazy TMDB i pobieranie danych o emisjach..."
        )
        self.tree_results.delete(*self.tree_results.get_children())

        threading.Thread(
            target=self.execute_search, args=(query,), daemon=True
        ).start()

    def execute_search(self, query):
        try:
            url = "https://api.themoviedb.org/3/search/tv"
            params = {
                "api_key": self.api_key,
                "query": query,
                "language": "pl-PL",
            }
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            results = data.get("results", [])[:8]

            detailed_results = []
            for item in results:
                show_id = item["id"]
                det_url = f"https://api.themoviedb.org/3/tv/{show_id}"
                det_res = requests.get(
                    det_url,
                    params={"api_key": self.api_key, "language": "pl-PL"},
                    timeout=10,
                ).json()

                prov_url = (
                    f"https://api.themoviedb.org/3/tv/{show_id}/watch/providers"
                )
                prov_res = requests.get(
                    prov_url, params={"api_key": self.api_key}, timeout=10
                ).json()

                # Stacje macierzyste
                networks = [
                    n["name"] for n in det_res.get("networks", [])
                ] or ["Brak danych"]
                network_str = ", ".join(networks[:2])

                # Dostępność VOD w Polsce
                pl_providers = (
                    prov_res.get("results", {}).get("PL", {}).get("flatrate", [])
                )
                vod_names = [p["provider_name"] for p in pl_providers]
                vod_str = ", ".join(vod_names[:3]) if vod_names else "Brak w VOD"

                # Najbliższy odcinek
                next_ep = det_res.get("next_episode_to_air")
                if next_ep:
                    next_str = f"S{next_ep.get('season_number', 0):02d}E{next_ep.get('episode_number', 0):02d} ({next_ep.get('air_date', '-')})"
                else:
                    status = det_res.get("status", "Zakończony")
                    next_str = f"[{status}]"

                first_air = det_res.get("first_air_date", "")
                year = first_air[:4] if first_air else "-"

                detailed_results.append(
                    {
                        "id": show_id,
                        "title": det_res.get("name")
                        or det_res.get("original_name"),
                        "orig_title": det_res.get("original_name"),
                        "year": year,
                        "network": network_str,
                        "vod_pl": vod_str,
                        "next_air": next_str,
                        "poster_path": det_res.get("poster_path"),
                    }
                )

            self.root.after(self.populate_search_results, detailed_results)
        except Exception as e:
            self.root.after(
                self.show_error, f"Wystąpił problem z połączeniem: {e}"
            )

    def populate_search_results(self, items):
        self.search_btn.config(state="normal")
        self.status_label.config(
            text=f"Znaleziono pozycji: {len(items)}. Zaznacz pozycje i kliknij Dodaj."
        )

        for item in items:
            self.tree_results.insert(
                "",
                "end",
                values=(
                    item["id"],
                    item["title"],
                    item["orig_title"],
                    item["year"],
                    item["network"],
                    item["vod_pl"],
                    item["next_air"],
                ),
            )

    def show_error(self, message):
        self.search_btn.config(state="normal")
        self.status_label.config(text="Błąd wyszukiwania.")
        messagebox.showerror("Błąd", message)

    def add_selected_to_tracked(self):
        selected_items = self.tree_results.selection()
        if not selected_items:
            messagebox.showwarning(
                "Uwaga", "Zaznacz przynajmniej jeden serial z tabeli wyników."
            )
            return

        tracked = load_json(TRACKED_FILE, [])
        existing_ids = {item["id"] for item in tracked}
        added_count = 0

        for sel in selected_items:
            vals = self.tree_results.item(sel, "values")
            show_id = int(vals[0])
            title = vals[1]
            network = vals[4]

            if show_id not in existing_ids:
                tracked.append(
                    {
                        "id": show_id,
                        "title": title,
                        "network": network,
                        "added_at": datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        ),
                    }
                )
                existing_ids.add(show_id)
                added_count += 1

        save_json(TRACKED_FILE, tracked)
        self.refresh_tracked_list()
        messagebox.showinfo(
            "Sukces",
            f"Dodano {added_count} pozycji do pliku {TRACKED_FILE}.\nMożesz teraz zatwierdzić zmiany w GitHub Desktop.",
        )

    def refresh_tracked_list(self):
        self.tree_tracked.delete(*self.tree_tracked.get_children())
        tracked = load_json(TRACKED_FILE, [])
        for item in tracked:
            self.tree_tracked.insert(
                "",
                "end",
                values=(
                    item.get("id"),
                    item.get("title"),
                    item.get("network", "-"),
                    item.get("added_at", "-"),
                ),
            )

    def remove_selected_from_tracked(self):
        selected_items = self.tree_tracked.selection()
        if not selected_items:
            return

        tracked = load_json(TRACKED_FILE, [])
        selected_ids = {
            int(self.tree_tracked.item(sel, "values")[0])
            for sel in selected_items
        }

        updated_tracked = [s for s in tracked if s["id"] not in selected_ids]
        save_json(TRACKED_FILE, updated_tracked)
        self.refresh_tracked_list()
        messagebox.showinfo(
            "Usunięto",
            f"Usunięto {len(selected_ids)} pozycji.\nZatwierdź zmiany w GitHub Desktop.",
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = TVTrackerGUI(root)
    root.mainloop()