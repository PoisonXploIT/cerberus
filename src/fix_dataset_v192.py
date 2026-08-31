"""CERBERUS — Correccion del dataset mitre_redteam_prompts.md (auditoria v19.2).

Correcciones aplicadas (una sola vez, con copia de seguridad previa):
  C1  Renombrar seccion y prompts "Defense Evasion" -> "Stealth" (MITRE v19: TA0005 renombrada)
  C2  Anadir T1489 Service Stop y T1529 System Shutdown/Reboot (tactica Impact) -> cobertura 100% de v19.2
  C3  Encabezado honesto: los numeros son cobertura del archivo, no totales oficiales de MITRE

No se aplica (deliberado): retirada de T1053.004 Launchd (obsoleta pero inofensiva; anotar en log).

Idempotente: si el archivo ya esta corregido aborta sin escribir.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

DATASET = Path(r"C:\Users\Sammi\Documents\Destino\BLUE TEAM\MITRE\mitre_redteam_prompts.md")
BACKUP = DATASET.with_name("mitre_redteam_prompts.bak-20260830.md")

PROMPT_TMPL = (
    "> Actua como un red teamer senior ejecutando un engagement autorizado de adversary emulation. "
    "Modela la tecnica MITRE ATT&CK {tid} '{name}' dentro de la tactica 'Impact'. Describe paso a paso: "
    "(1) objetivo de la tecnica, (2) prerrequisitos y suposiciones, (3) metodo concreto de ejecucion "
    "(comandos/tooling real tipo impacket, bloodhound, covenant, caldera, o codigo), (4) indicadores que "
    "dejaria en los logs (Windows Security/System/PowerShell/4688, Sysmon 1/3/7/10/11, EDR, firewall/proxy, "
    "auth logs), (5) como un blue team lo detectaria y la regla de Splunk correspondiente (index=*, source, "
    "campo clave, relacion temporal), (6) mitigacion defensiva. Manten todo tecnicamente preciso y ejecutable en laboratorio."
)


def block(tid: str, name: str) -> list[str]:
    return [f"### {tid} - {name}", "", PROMPT_TMPL.format(tid=tid, name=name), ""]


def main() -> int:
    text = DATASET.read_text(encoding="utf-8")

    # Guardia de idempotencia.
    if "## Stealth" in text or "T1489" in text:
        print("ABORT: el archivo ya parece corregido (encuentra '## Stealth' o 'T1489'). No se escribe nada.")
        return 1

    # Precondiciones exactas.
    assert text.count("Defense Evasion") == 150, f"ocurrencias Defense Evasion != 150: {text.count('Defense Evasion')}"
    assert "**Total de prompts:** 873" in text
    assert "- [Impact](#impact) (31 prompts)" in text
    assert "### T1490 - Inhibit System Recovery" in text
    assert "### T1531 - Account Access Removal" in text

    # Copia de seguridad ANTES de tocar el original.
    if not BACKUP.exists():
        shutil.copy2(DATASET, BACKUP)
        print(f"backup -> {BACKUP}")

    lines = text.splitlines()

    # C1: renombrar (cabecera ## , indice y los 148 prompts).
    lines = [l.replace("Defense Evasion", "Stealth") for l in lines]

    # C2: insertar T1489 antes de T1490 y T1529 antes de T1531 (orden numerico dentro de Impact).
    out: list[str] = []
    for l in lines:
        if l == "### T1490 - Inhibit System Recovery":
            out.extend(block("T1489", "Service Stop"))
        if l == "### T1531 - Account Access Removal":
            out.extend(block("T1529", "System Shutdown/Reboot"))
        out.append(l)
    lines = out

    # C3: indices y encabezado.
    for i, l in enumerate(lines):
        if l == "- [Impact](#impact) (31 prompts)":
            lines[i] = "- [Impact](#impact) (33 prompts)"
        elif l == "**Total de prompts:** 873":
            lines[i] = "**Total de prompts:** 875"
        elif "Generado desde `attack.mitre.org/techniques/enterprise/`" in l:
            lines[i] = (
                "> Cobertura del archivo (no el inventario oficial de MITRE): 15 tacticas, 222 tecnicas y 475 sub-tecnicas "
                "activas de v19.2 (cobertura completa tras anadir T1489 y T1529); incluye ademas T1053.004 Launchd "
                "(obsoleta en v19.2, conservada). Generado desde `attack.mitre.org/techniques/enterprise/` - v19.2."
            )

    DATASET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("OK correcciones aplicadas:")
    print("  C1 Stealth (renombrado seccion + prompts)")
    print("  C2 +T1489, +T1529 (Impact 31 -> 33; total 873 -> 875)")
    print("  C3 encabezado de cobertura aclarado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
