import os
import csv
import uuid
import shutil
import sqlite3
from typing import Optional
from PIL import Image
import customtkinter as ctk
from tkinter import filedialog, messagebox

DB_NAME = "almacen.db"
IMG_FOLDER = "imagenes_almacen"

os.makedirs(IMG_FOLDER, exist_ok=True)


# --- Base de Datos con Migración Automática ---
class DatabaseManager:
    @staticmethod
    def init_db() -> None:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS paquetes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_caja TEXT NOT NULL UNIQUE,
                    proyecto TEXT NOT NULL,
                    descripcion TEXT,
                    ubicacion TEXT NOT NULL,
                    imagen TEXT,
                    surtida TEXT NOT NULL DEFAULT 'No',
                    responsable TEXT NOT NULL,
                    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Migración: Agrega la columna 'surtida' automáticamente si la BD era de una versión anterior
            cursor.execute("PRAGMA table_info(paquetes)")
            columnas = [columna[1] for columna in cursor.fetchall()]
            if "surtida" not in columnas:
                cursor.execute("ALTER TABLE paquetes ADD COLUMN surtida TEXT NOT NULL DEFAULT 'No'")
            
            conn.commit()

    @staticmethod
    def existe_numero_caja(caja: str, id_ignorar: Optional[int] = None) -> bool:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            if id_ignorar:
                cursor.execute("SELECT 1 FROM paquetes WHERE numero_caja = ? AND id != ?", (caja, id_ignorar))
            else:
                cursor.execute("SELECT 1 FROM paquetes WHERE numero_caja = ?", (caja,))
            return cursor.fetchone() is not None

    @staticmethod
    def guardar_paquete(caja: str, proyecto: str, desc: str, ubicacion: str, img: str, resp: str) -> None:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO paquetes (numero_caja, proyecto, descripcion, ubicacion, imagen, surtida, responsable)
                VALUES (?, ?, ?, ?, ?, 'No', ?)
            """, (caja, proyecto, desc, ubicacion, img, resp))
            conn.commit()

    @staticmethod
    def cambiar_estado_surtida(id_paquete: int, nuevo_estado: str) -> None:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE paquetes SET surtida=? WHERE id=?", (nuevo_estado, id_paquete))
            conn.commit()

    @staticmethod
    def actualizar_paquete(id_paquete: int, caja: str, proyecto: str, desc: str, ubicacion: str, img: str, surtida: str, resp: str) -> None:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE paquetes 
                SET numero_caja=?, proyecto=?, descripcion=?, ubicacion=?, imagen=?, surtida=?, responsable=?
                WHERE id=?
            """, (caja, proyecto, desc, ubicacion, img, surtida, resp, id_paquete))
            conn.commit()

    @staticmethod
    def eliminar_paquete(id_paquete: int) -> Optional[str]:
        """Elimina el registro de la BD y retorna la ruta de la imagen para su borrado físico."""
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT imagen FROM paquetes WHERE id=?", (id_paquete,))
            res = cursor.fetchone()
            img_path = res[0] if res else None

            cursor.execute("DELETE FROM paquetes WHERE id=?", (id_paquete,))
            conn.commit()
            return img_path

    @staticmethod
    def obtener_paquetes(filtro: str = "", estado: str = "Todos") -> list:
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            query = """
                SELECT id, numero_caja, proyecto, descripcion, ubicacion, imagen, surtida, responsable 
                FROM paquetes 
                WHERE (numero_caja LIKE ? OR proyecto LIKE ? OR ubicacion LIKE ? OR responsable LIKE ?)
            """
            pattern = f"%{filtro}%"
            params = [pattern, pattern, pattern, pattern]

            if estado in ["Sí", "No"]:
                query += " AND surtida = ?"
                params.append(estado)

            query += " ORDER BY id DESC"
            cursor.execute(query, params)
            return cursor.fetchall()


# --- Visor de Imagen ---
class VisorImagen(ctk.CTkToplevel):
    def __init__(self, parent, path_imagen: str):
        super().__init__(parent)
        self.title("Vista Previa de Imagen")
        self.geometry("600x600")
        self.grab_set()

        try:
            pil_img = Image.open(path_imagen)
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(550, 550))
            lbl = ctk.CTkLabel(self, image=ctk_img, text="")
            lbl.pack(expand=True, fill="both", padx=10, pady=10)
        except Exception:
            ctk.CTkLabel(self, text="Error al cargar la imagen").pack(expand=True)


# --- Captura / Edición de Paquete ---
class VentanaCaptura(ctk.CTkToplevel):
    def __init__(self, parent, datos_editar: Optional[tuple] = None):
        super().__init__(parent)
        self.datos_editar = datos_editar
        self.title("Editar Paquete" if datos_editar else "Capturar Nuevo Paquete")
        self.geometry("600x680")
        self.resizable(False, False)
        self.grab_set()

        self.imagen_path = ctk.StringVar()
        self.surtida_var = ctk.StringVar(value="No")

        self._crear_interfaz()

        if self.datos_editar:
            self._cargar_datos_edicion()

    def _crear_interfaz(self) -> None:
        main_frame = ctk.CTkFrame(self, corner_radius=15)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        titulo = "Editar Registro" if self.datos_editar else "Ingreso de Caja al Almacén"
        ctk.CTkLabel(main_frame, text=titulo, font=("Segoe UI", 20, "bold")).pack(pady=(15, 5))

        self.lbl_error = ctk.CTkLabel(main_frame, text="", font=("Segoe UI", 12), text_color="#e74c3c")
        self.lbl_error.pack(pady=(0, 10))

        self.entry_caja = ctk.CTkEntry(main_frame, placeholder_text="Número de Caja *", width=400)
        self.entry_caja.pack(pady=6)

        self.entry_proyecto = ctk.CTkEntry(main_frame, placeholder_text="Proyecto *", width=400)
        self.entry_proyecto.pack(pady=6)

        self.entry_ubicacion = ctk.CTkEntry(main_frame, placeholder_text="Ubicación en Almacén *", width=400)
        self.entry_ubicacion.pack(pady=6)

        self.entry_responsable = ctk.CTkEntry(main_frame, placeholder_text="Responsable de ingreso *", width=400)
        self.entry_responsable.pack(pady=6)

        ctk.CTkLabel(main_frame, text="Descripción del contenido:", font=("Segoe UI", 11)).pack(anchor="w", padx=80, pady=(4, 0))
        self.txt_descripcion = ctk.CTkTextbox(main_frame, width=400, height=80)
        self.txt_descripcion.pack(pady=6)

        # Imagen
        frame_img = ctk.CTkFrame(main_frame, fg_color="transparent")
        frame_img.pack(pady=6)
        
        self.entry_imagen = ctk.CTkEntry(frame_img, textvariable=self.imagen_path, placeholder_text="Ruta de imagen (Opcional)", width=280, state="readonly")
        self.entry_imagen.pack(side="left", padx=(0, 5))
        
        btn_img = ctk.CTkButton(frame_img, text="📷 Buscar", width=115, command=self._seleccionar_imagen)
        btn_img.pack(side="right")

        if self.datos_editar:
            check_surtida = ctk.CTkCheckBox(main_frame, text="¿Caja totalmente surtida?", variable=self.surtida_var, onvalue="Sí", offvalue="No")
            check_surtida.pack(pady=10)

        texto_btn = "💾 Actualizar Paquete" if self.datos_editar else "💾 Guardar Paquete"
        btn_guardar = ctk.CTkButton(main_frame, text=texto_btn, font=("Segoe UI", 14, "bold"), height=40, width=400, command=self._guardar)
        btn_guardar.pack(pady=(15, 15))

    def _cargar_datos_edicion(self) -> None:
        _, caja, proyecto, desc, ubicacion, img, surtida, resp = self.datos_editar
        self.entry_caja.insert(0, caja)
        self.entry_proyecto.insert(0, proyecto)
        self.entry_ubicacion.insert(0, ubicacion)
        self.entry_responsable.insert(0, resp)
        self.txt_descripcion.insert("1.0", desc)
        self.imagen_path.set(img)
        self.surtida_var.set(surtida)

    def _seleccionar_imagen(self) -> None:
        archivo = filedialog.askopenfilename(filetypes=[("Imágenes", "*.png;*.jpg;*.jpeg;*.webp")])
        if archivo:
            # Generar un nombre único con UUID para evitar sobreescritura
            ext = os.path.splitext(archivo)[1]
            nombre_unico = f"{uuid.uuid4().hex}{ext}"
            destino = os.path.join(IMG_FOLDER, nombre_unico)
            try:
                shutil.copy(archivo, destino)
                self.imagen_path.set(destino)
            except Exception:
                self.imagen_path.set(archivo)

    def _guardar(self) -> None:
        caja = self.entry_caja.get().strip()
        proyecto = self.entry_proyecto.get().strip()
        ubicacion = self.entry_ubicacion.get().strip()
        responsable = self.entry_responsable.get().strip()
        descripcion = self.txt_descripcion.get("1.0", "end-1c").strip()

        if not caja or not proyecto or not ubicacion or not responsable:
            self.lbl_error.configure(text="⚠️ Por favor completa los campos marcados con (*)")
            return

        id_p = self.datos_editar[0] if self.datos_editar else None
        if DatabaseManager.existe_numero_caja(caja, id_ignorar=id_p):
            self.lbl_error.configure(text=f"⚠️ El número de caja '{caja}' ya se encuentra registrado.")
            return

        try:
            if self.datos_editar:
                DatabaseManager.actualizar_paquete(id_p, caja, proyecto, descripcion, ubicacion, self.imagen_path.get(), self.surtida_var.get(), responsable)
                messagebox.showinfo("Éxito", "Registro actualizado.", parent=self)
            else:
                DatabaseManager.guardar_paquete(caja, proyecto, descripcion, ubicacion, self.imagen_path.get(), responsable)
                messagebox.showinfo("Éxito", "Paquete ingresado correctamente.", parent=self)
                
            self.destroy()
        except Exception as e:
            self.lbl_error.configure(text=f"Error en la base de datos: {e}")


# --- Historial y Consultas ---
class VentanaHistorial(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Historial de Entregas y Almacén")
        self.geometry("1080x700")
        self.grab_set()

        self._crear_interfaz()
        self._cargar_registros()

    def _crear_interfaz(self) -> None:
        top_frame = ctk.CTkFrame(self, corner_radius=10)
        top_frame.pack(fill="x", padx=15, pady=10)

        self.entry_buscar = ctk.CTkEntry(top_frame, placeholder_text="🔍 Buscar por caja, proyecto, ubicación...", width=300)
        self.entry_buscar.pack(side="left", padx=10, pady=10)
        self.entry_buscar.bind("<KeyRelease>", lambda e: self._cargar_registros())

        self.combo_estado = ctk.CTkOptionMenu(top_frame, values=["Todos", "Surtidas", "Pendientes"], command=lambda _: self._cargar_registros(), width=130)
        self.combo_estado.set("Todos")
        self.combo_estado.pack(side="left", padx=5, pady=10)

        btn_exportar = ctk.CTkButton(top_frame, text="📊 Exportar CSV", fg_color="#27ae60", hover_color="#219150", width=130, command=self._exportar_csv)
        btn_exportar.pack(side="right", padx=10, pady=10)

        self.lbl_kpi = ctk.CTkLabel(top_frame, text="Total: 0 | Surtidas: 0%", font=("Segoe UI", 12, "bold"))
        self.lbl_kpi.pack(side="right", padx=15)

        self.scroll_frame = ctk.CTkScrollableFrame(self, label_text="Registros Encontrados", label_font=("Segoe UI", 14, "bold"))
        self.scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def _cargar_registros(self) -> None:
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        filtro = self.entry_buscar.get().strip()
        estado_map = {"Todos": "Todos", "Surtidas": "Sí", "Pendientes": "No"}
        estado_sel = estado_map.get(self.combo_estado.get(), "Todos")

        registros = DatabaseManager.obtener_paquetes(filtro, estado_sel)

        total = len(registros)
        surtidas = sum(1 for r in registros if r[6] == "Sí")
        pct = (surtidas / total * 100) if total > 0 else 0
        self.lbl_kpi.configure(text=f"Total: {total} | Surtidas: {pct:.1f}%")

        if not registros:
            ctk.CTkLabel(self.scroll_frame, text="No se encontraron registros.", font=("Segoe UI", 13)).pack(pady=20)
            return

        for reg in registros:
            self._agregar_card(reg)

    def _agregar_card(self, reg: tuple) -> None:
        id_p, caja, proyecto, desc, ubicacion, img_path, surtida, resp = reg

        card = ctk.CTkFrame(self.scroll_frame, corner_radius=10)
        card.pack(fill="x", pady=6, padx=5)
        card.columnconfigure(1, weight=1)

        ctk_img = self._cargar_imagen(img_path)
        if ctk_img:
            btn_img = ctk.CTkButton(card, image=ctk_img, text="", fg_color="transparent", hover=False, width=100, command=lambda: VisorImagen(self, img_path))
            btn_img.grid(row=0, column=0, rowspan=4, padx=10, pady=10)
        else:
            ctk.CTkLabel(card, text="🖼️ Sin Imagen", font=("Segoe UI", 11)).grid(row=0, column=0, rowspan=4, padx=15, pady=10)

        ctk.CTkLabel(card, text=f"📦 Caja: {caja}  |  Proyecto: {proyecto}", font=("Segoe UI", 14, "bold"), anchor="w").grid(row=0, column=1, sticky="w", pady=(8, 2))
        ctk.CTkLabel(card, text=f"📍 Ubicación: {ubicacion}  |  👤 Responsable: {resp}", font=("Segoe UI", 12), text_color="gray70", anchor="w").grid(row=1, column=1, sticky="w")
        ctk.CTkLabel(card, text=f"📝 {desc}", font=("Segoe UI", 12), anchor="w", wraplength=400, justify="left").grid(row=2, column=1, sticky="w", pady=4)

        color_surtida = "#2ecc71" if surtida == "Sí" else "#e74c3c"
        ctk.CTkLabel(card, text=f"Surtida: {surtida}", font=("Segoe UI", 12, "bold"), text_color=color_surtida).grid(row=3, column=1, sticky="w", pady=(0, 8))

        # Acciones rápidas
        frame_acciones = ctk.CTkFrame(card, fg_color="transparent")
        frame_acciones.grid(row=0, column=2, rowspan=4, padx=10, pady=10)

        texto_surtir = "✅ Marcar Surtida" if surtida == "No" else "↩️ Marcar Pendiente"
        color_btn_surtir = "#27ae60" if surtida == "No" else "#e67e22"
        
        btn_surtir = ctk.CTkButton(
            frame_acciones, text=texto_surtir, fg_color=color_btn_surtir, width=130, height=30,
            command=lambda: self._toggle_surtida(id_p, "Sí" if surtida == "No" else "No")
        )
        btn_surtir.pack(pady=2)

        btn_edit = ctk.CTkButton(frame_acciones, text="✏️ Editar", width=130, height=30, command=lambda: self._editar(reg))
        btn_edit.pack(pady=2)

        btn_del = ctk.CTkButton(frame_acciones, text="🗑️ Eliminar", width=130, height=30, fg_color="#c0392b", hover_color="#962d22", command=lambda: self._eliminar(id_p))
        btn_del.pack(pady=2)

    def _toggle_surtida(self, id_paquete: int, nuevo_estado: str) -> None:
        DatabaseManager.cambiar_estado_surtida(id_paquete, nuevo_estado)
        self._cargar_registros()

    def _cargar_imagen(self, path: str) -> Optional[ctk.CTkImage]:
        if path and os.path.exists(path):
            try:
                pil_img = Image.open(path)
                return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(90, 90))
            except Exception:
                return None
        return None

    def _editar(self, reg: tuple) -> None:
        ventana = VentanaCaptura(self, datos_editar=reg)
        self.wait_window(ventana)
        self._cargar_registros()

    def _eliminar(self, id_paquete: int) -> None:
        if messagebox.askyesno("Confirmar", "¿Eliminar este paquete permanentemente?", parent=self):
            img_path = DatabaseManager.eliminar_paquete(id_paquete)
            # Borrar la imagen físicamente si existía en la carpeta de imágenes
            if img_path and os.path.exists(img_path):
                try:
                    os.remove(img_path)
                except OSError:
                    pass
            self._cargar_registros()

    def _exportar_csv(self) -> None:
        registros = DatabaseManager.obtener_paquetes()
        if not registros:
            messagebox.showwarning("Sin datos", "No hay datos para exportar.", parent=self)
            return

        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            with open(path, mode="w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["ID", "Caja", "Proyecto", "Descripción", "Ubicación", "Imagen", "Surtida", "Responsable"])
                writer.writerows(registros)
            messagebox.showinfo("Exportado", "Datos exportados correctamente.", parent=self)


# --- Aplicación Principal ---
class AlmacenApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Sistema Integral de Almacén")
        self.geometry("480x380")
        self.resizable(False, False)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")

        DatabaseManager.init_db()
        self._crear_ui()

    def _crear_ui(self) -> None:
        main_frame = ctk.CTkFrame(self, corner_radius=15)
        main_frame.pack(fill="both", expand=True, padx=25, pady=25)

        ctk.CTkLabel(main_frame, text="📦 Control de Almacén", font=("Segoe UI", 24, "bold")).pack(pady=(25, 20))

        btn_captura = ctk.CTkButton(
            main_frame, text="➕ Capturar Paquete", font=("Segoe UI", 15, "bold"),
            height=50, width=280, command=lambda: VentanaCaptura(self)
        )
        btn_captura.pack(pady=10)

        btn_historial = ctk.CTkButton(
            main_frame, text="📜 Historial y Consultas", font=("Segoe UI", 15, "bold"),
            fg_color="transparent", border_width=2, height=50, width=280, command=lambda: VentanaHistorial(self)
        )
        btn_historial.pack(pady=10)


if __name__ == "__main__":
    app = AlmacenApp()
    app.mainloop()