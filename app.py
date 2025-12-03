import streamlit as st
from db import init_db, run_query, fetch_all
import pandas as pd
from datetime import datetime, date
from fpdf import FPDF
import io

st.set_page_config(page_title="Gabinet lekarski", layout="wide")
init_db()

# ------------------------
# Helper: wyszukiwanie ICD
# ------------------------
def search_icd(q: str) -> pd.DataFrame:
    q = q.strip()
    if len(q) < 2:
        return pd.DataFrame(columns=["code", "name"])
    return fetch_all(
        "SELECT code, name FROM icd10 WHERE code LIKE ? OR name LIKE ? ORDER BY code LIMIT 20",
        (f"%{q}%", f"%{q}%"),
    )

# ------------------------
# Helper: PDF export wizyty
# ------------------------
def generate_visit_pdf(visit_details: pd.Series, diagnoses: pd.DataFrame) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Karta wizyty", ln=1)

    pdf.set_font("Arial", "", 11)
    pdf.ln(4)
    pdf.cell(0, 6, f"Pacjent: {visit_details['first_name']} {visit_details['last_name']}", ln=1)
    pdf.cell(0, 6, f"PESEL: {visit_details['pesel']}", ln=1)
    pdf.cell(0, 6, f"Data wizyty: {visit_details['date']}", ln=1)
    pdf.ln(4)

    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 6, "Rozpoznania ICD-10:", ln=1)
    pdf.set_font("Arial", "", 11)
    if diagnoses.empty:
        pdf.cell(0, 6, "- brak", ln=1)
    else:
        for _, row in diagnoses.iterrows():
            pref = "[GŁÓWNE] " if row["is_primary"] == 1 else ""
            line = f"{pref}{row['icd_code']} – {row['icd_name']}"
            pdf.multi_cell(0, 5, line)
    pdf.ln(3)

    def section(title: str, text: str):
        pdf.set_font("Arial", "B", 11)
        pdf.cell(0, 6, title, ln=1)
        pdf.set_font("Arial", "", 11)
        if text:
            for line in text.splitlines():
                pdf.multi_cell(0, 5, line)
        else:
            pdf.cell(0, 5, "-", ln=1)
        pdf.ln(2)

    section("Wywiad:", visit_details.get("interview") or "")
    section("Badanie:", visit_details.get("examination") or "")
    section("Leki:", visit_details.get("medications") or "")
    section("Zalecenia:", visit_details.get("recommendations") or "")

    pdf_bytes = pdf.output(dest="S").encode("latin-1")
    return pdf_bytes

# ------------------------
# Sidebar – nawigacja
# ------------------------
st.sidebar.title("Gabinet")
menu = st.sidebar.radio(
    "Nawigacja",
    [
        "Dashboard",
        "Nowy pacjent",
        "Lista pacjentów",
        "Nowa wizyta",
        "Wizyty – przegląd/edycja",
        "Kalendarz wizyt",
    ]
)

# ------------------------
# DASHBOARD
# ------------------------
if menu == "Dashboard":
    st.title("Panel lekarza – dashboard")

    col1, col2 = st.columns(2)
    n_patients = fetch_all("SELECT COUNT(*) AS n FROM patients")["n"][0]
    n_visits = fetch_all("SELECT COUNT(*) AS n FROM visits")["n"][0]
    col1.metric("Liczba pacjentów", n_patients)
    col2.metric("Liczba wizyt", n_visits)

# ------------------------
# NOWY PACJENT – FORMULARZ
# ------------------------
elif menu == "Nowy pacjent":
    st.title("Rejestracja pacjenta")

    with st.form("new_patient_form"):
        col1, col2 = st.columns(2)
        with col1:
            first_name = st.text_input("Imię")
            pesel = st.text_input("PESEL")
            phone = st.text_input("Telefon")
        with col2:
            last_name = st.text_input("Nazwisko")
            address = st.text_input("Adres")
            email = st.text_input("E-mail")

        submitted = st.form_submit_button("Zapisz pacjenta")

        if submitted:
            errors = []
            if not first_name:
                errors.append("Brak imienia.")
            if not last_name:
                errors.append("Brak nazwiska.")
            if not pesel:
                errors.append("Brak PESEL.")
            if errors:
                for e in errors:
                    st.error(e)
            else:
                run_query(
                    """
                    INSERT INTO patients (first_name, last_name, pesel, address, phone, email, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (first_name, last_name, pesel, address, phone, email, datetime.now().isoformat()),
                )
                st.success("Pacjent zapisany.")

# ------------------------
# LISTA PACJENTÓW + PODGLĄD
# ------------------------
elif menu == "Lista pacjentów":
    st.title("Lista pacjentów")

    search = st.text_input("Szukaj (nazwisko / imię / PESEL)")
    if search:
        like = f"%{search}%"
        patients = fetch_all(
            """
            SELECT * FROM patients
            WHERE last_name LIKE ? OR first_name LIKE ? OR pesel LIKE ?
            ORDER BY last_name, first_name
            """,
            (like, like, like),
        )
    else:
        patients = fetch_all("SELECT * FROM patients ORDER BY last_name, first_name")

    st.dataframe(patients, use_container_width=True)

    if not patients.empty:
        st.subheader("Karta pacjenta")
        selected = st.selectbox(
            "Wybierz pacjenta",
            patients.itertuples(),
            format_func=lambda p: f"{p.last_name} {p.first_name} ({p.pesel})",
        )

        st.write(f"**Imię i nazwisko:** {selected.first_name} {selected.last_name}")
        st.write(f"**PESEL:** {selected.pesel}")
        st.write(f"**Adres:** {selected.address}")
        st.write(f"**Telefon:** {selected.phone}")
        st.write(f"**E-mail:** {selected.email}")

        visits = fetch_all(
            """
            SELECT v.id, v.date
            FROM visits v
            WHERE v.patient_id = ?
            ORDER BY v.date DESC
            """,
            (selected.id,),
        )
        st.subheader("Wizyty")
        if visits.empty:
            st.info("Brak wizyt.")
        else:
            st.table(visits)

# ------------------------
# NOWA WIZYTA – FORMULARZ
# ------------------------
elif menu == "Nowa wizyta":
    st.title("Nowa wizyta")

    patients = fetch_all("SELECT id, first_name, last_name, pesel FROM patients ORDER BY last_name, first_name")
    if patients.empty:
        st.warning("Brak pacjentów. Najpierw dodaj pacjenta.")
    else:
        selected = st.selectbox(
            "Pacjent",
            patients.itertuples(),
            format_func=lambda p: f"{p.last_name} {p.first_name} ({p.pesel})",
        )

        with st.form("new_visit_form"):
            st.markdown(f"**Pacjent:** {selected.first_name} {selected.last_name} ({selected.pesel})")

            interview = st.text_area("Wywiad", height=120)
            examination = st.text_area("Badanie", height=120)
            medications = st.text_area("Leki")
            recommendations = st.text_area("Zalecenia")

            st.markdown("### Rozpoznania ICD-10")

            dx_entries = []
            for i in range(3):
                st.markdown(f"**Rozpoznanie {i+1}**")
                q = st.text_input(f"Szukaj kodu / nazwy ({i+1})", key=f"icd_search_{i}")
                results = search_icd(q) if q else pd.DataFrame()

                if not results.empty:
                    st.dataframe(results, use_container_width=True, height=150)

                code = st.text_input(f"Kod ICD ({i+1})", key=f"icd_code_{i}")
                name = st.text_input(f"Nazwa ICD ({i+1})", key=f"icd_name_{i}")
                primary = st.checkbox("Główne rozpoznanie", key=f"icd_primary_{i}", value=(i == 0))

                if code and name:
                    dx_entries.append((code, name, primary))

                st.markdown("---")

            submitted = st.form_submit_button("Zapisz wizytę")

            if submitted:
                if not interview and not examination and not dx_entries:
                    st.error("Wypełnij przynajmniej część danych wizyty.")
                else:
                    run_query(
                        """
                        INSERT INTO visits (patient_id, date, interview, examination, medications, recommendations)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            selected.id,
                            datetime.now().isoformat(),
                            interview,
                            examination,
                            medications,
                            recommendations,
                        ),
                    )
                    visit_id = fetch_all("SELECT last_insert_rowid() AS id")["id"][0]

                    for code, name, primary in dx_entries:
                        run_query(
                            """
                            INSERT INTO diagnoses (visit_id, icd_code, icd_name, is_primary)
                            VALUES (?, ?, ?, ?)
                            """,
                            (visit_id, code, name, 1 if primary else 0),
                        )

                    st.success("Wizyta zapisana.")

# ------------------------
# WIZYTY – PRZEGLĄD / EDYCJA + PDF
# ------------------------
elif menu == "Wizyty – przegląd/edycja":
    st.title("Wizyty – przegląd i edycja")

    colf1, colf2 = st.columns(2)
    with colf1:
        patient_filter = st.text_input("Filtr pacjenta (nazwisko / PESEL)")
    with colf2:
        date_from = st.date_input("Od daty", value=None, key="vf_from")
        date_to = st.date_input("Do daty", value=None, key="vf_to")

    query = """
        SELECT v.id, v.date, p.last_name, p.first_name, p.pesel
        FROM visits v
        JOIN patients p ON p.id = v.patient_id
        WHERE 1=1
    """
    params = []

    if patient_filter:
        like = f"%{patient_filter}%"
        query += " AND (p.last_name LIKE ? OR p.first_name LIKE ? OR p.pesel LIKE ?)"
        params.extend([like, like, like])

    if isinstance(date_from, date):
        query += " AND date(v.date) >= date(?)"
        params.append(date_from.isoformat())
    if isinstance(date_to, date):
        query += " AND date(v.date) <= date(?)"
        params.append(date_to.isoformat())

    query += " ORDER BY v.date DESC"

    visits = fetch_all(query, tuple(params))

    st.subheader("Lista wizyt")
    if visits.empty:
        st.info("Brak wizyt dla zadanych filtrów.")
    else:
        st.dataframe(visits, use_container_width=True)

        selected_visit = st.selectbox(
            "Wybierz wizytę do podglądu / edycji",
            visits.itertuples(),
            format_func=lambda v: f"{v.date} – {v.last_name} {v.first_name} ({v.pesel}) [ID {v.id}]",
        )

        visit_details = fetch_all(
            """
            SELECT v.*, p.first_name, p.last_name, p.pesel
            FROM visits v
            JOIN patients p ON p.id = v.patient_id
            WHERE v.id = ?
            """,
            (selected_visit.id,),
        ).iloc[0]

        diagnoses = fetch_all(
            """
            SELECT icd_code, icd_name, is_primary
            FROM diagnoses
            WHERE visit_id = ?
            ORDER BY is_primary DESC, icd_code
            """,
            (selected_visit.id,),
        )

        st.subheader("Szczegóły wizyty")
        st.markdown(f"**Pacjent:** {visit_details['first_name']} {visit_details['last_name']} ({visit_details['pesel']})")
        st.markdown(f"**Data wizyty:** {visit_details['date']}")

        st.markdown("**Rozpoznania ICD-10:**")
        if diagnoses.empty:
            st.write("Brak rozpoznań.")
        else:
            for _, row in diagnoses.iterrows():
                pref = "[GŁÓWNE] " if row["is_primary"] == 1 else ""
                st.write(f"{pref}{row['icd_code']} – {row['icd_name']}")

        st.markdown("**Wywiad:**")
        st.write(visit_details["interview"])

        st.markdown("**Badanie:**")
        st.write(visit_details["examination"])

        st.markdown("**Leki:**")
        st.write(visit_details["medications"])

        st.markdown("**Zalecenia:**")
        st.write(visit_details["recommendations"])

        pdf_bytes = generate_visit_pdf(visit_details, diagnoses)
        st.download_button(
            "Pobierz PDF wizyty",
            data=pdf_bytes,
            file_name=f"wizyta_{selected_visit.id}.pdf",
            mime="application/pdf",
        )

        st.markdown("---")
        st.subheader("Edycja wizyty")

        with st.form("edit_visit_form"):
            interview_edit = st.text_area("Wywiad", value=visit_details["interview"] or "", height=120)
            exam_edit = st.text_area("Badanie", value=visit_details["examination"] or "", height=120)
            meds_edit = st.text_area("Leki", value=visit_details["medications"] or "")
            rec_edit = st.text_area("Zalecenia", value=visit_details["recommendations"] or "")

            st.markdown("**Rozpoznania (nadpisanie listy):**")
            dx_codes = []
            dx_names = []
            dx_primary_idx = 0

            existing = diagnoses.reset_index(drop=True)
            for i in range(3):
                if i < len(existing):
                    default_code = existing.loc[i, "icd_code"]
                    default_name = existing.loc[i, "icd_name"]
                    default_primary = existing.loc[i, "is_primary"] == 1
                else:
                    default_code = ""
                    default_name = ""
                    default_primary = (i == 0 and existing.empty)

                code_i = st.text_input(f"Kod ICD ({i+1})", value=default_code, key=f"edit_icd_code_{i}")
                name_i = st.text_input(f"Nazwa ICD ({i+1})", value=default_name, key=f"edit_icd_name_{i}")
                primary_i = st.checkbox("Główne", value=default_primary, key=f"edit_icd_primary_{i}")

                dx_codes.append(code_i)
                dx_names.append(name_i)
                if primary_i:
                    dx_primary_idx = i

            submitted_edit = st.form_submit_button("Zapisz zmiany")

            if submitted_edit:
                run_query(
                    """
                    UPDATE visits
                    SET interview = ?, examination = ?, medications = ?, recommendations = ?
                    WHERE id = ?
                    """,
                    (interview_edit, exam_edit, meds_edit, rec_edit, selected_visit.id),
                )
                run_query("DELETE FROM diagnoses WHERE visit_id = ?", (selected_visit.id,))

                for i, (code, name) in enumerate(zip(dx_codes, dx_names)):
                    code = code.strip()
                    name = name.strip()
                    if not code or not name:
                        continue
                    run_query(
                        """
                        INSERT INTO diagnoses (visit_id, icd_code, icd_name, is_primary)
                        VALUES (?, ?, ?, ?)
                        """,
                        (selected_visit.id, code, name, 1 if i == dx_primary_idx else 0),
                    )

                st.success("Wizyta zaktualizowana.")

# ------------------------
# KALENDARZ WIZYT
# ------------------------
elif menu == "Kalendarz wizyt":
    st.title("Kalendarz wizyt")

    selected_date = st.date_input("Wybierz dzień", value=date.today())

    visits = fetch_all(
        """
        SELECT v.id, v.date, p.last_name, p.first_name, p.pesel
        FROM visits v
        JOIN patients p ON p.id = v.patient_id
        WHERE date(v.date) = date(?)
        ORDER BY v.date
        """,
        (selected_date.isoformat(),),
    )

    if visits.empty:
        st.info("Brak wizyt w wybranym dniu.")
    else:
        st.subheader(f"Wizyty w dniu {selected_date.isoformat()}")
        st.dataframe(visits, use_container_width=True)

        selected_visit = st.selectbox(
            "Wybierz wizytę",
            visits.itertuples(),
            format_func=lambda v: f"{v.date} – {v.last_name} {v.first_name} ({v.pesel}) [ID {v.id}]",
        )

        visit_details = fetch_all(
            """
            SELECT v.*, p.first_name, p.last_name, p.pesel
            FROM visits v
            JOIN patients p ON p.id = v.patient_id
            WHERE v.id = ?
            """,
            (selected_visit.id,),
        ).iloc[0]

        diagnoses = fetch_all(
            """
            SELECT icd_code, icd_name, is_primary
            FROM diagnoses
            WHERE visit_id = ?
            ORDER BY is_primary DESC, icd_code
            """,
            (selected_visit.id,),
        )

        st.subheader("Szczegóły wizyty")
        st.markdown(f"**Pacjent:** {visit_details['first_name']} {visit_details['last_name']} ({visit_details['pesel']})")
        st.markdown(f"**Data wizyty:** {visit_details['date']}")

        st.markdown("**Rozpoznania ICD-10:**")
        if diagnoses.empty:
            st.write("Brak rozpoznań.")
        else:
            for _, row in diagnoses.iterrows():
                pref = "[GŁÓWNE] " if row["is_primary"] == 1 else ""
                st.write(f"{pref}{row['icd_code']} – {row['icd_name']}")

        st.markdown("**Wywiad:**")
        st.write(visit_details["interview"])

        st.markdown("**Badanie:**")
        st.write(visit_details["examination"])

        st.markdown("**Leki:**")
        st.write(visit_details["medications"])

        st.markdown("**Zalecenia:**")
        st.write(visit_details["recommendations"])