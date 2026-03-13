from typing import Optional
import os

# ---------------- PARAMETERS ----------------
LAYOUT_PATH = "deck.lay"

PLATE_NAME = "plate_96"
TIPS_NAME = "tips_200ul"
RESERVOIR_NAME = "reservoir"
WASTE_NAME: Optional[str] = "waste"

ROWS = "ABCDEFGH"
N_COLS = 12

PREFILL_VOL_UL = 100
TRANSFER_VOL_UL = 100
MIX_VOL_UL = 150
MIX_CYCLES = 3
PREMIX_START_CYCLES = 2
# --------------------------------------------

from pyhamilton import (
    HamiltonInterface,
    LayoutManager,
    STAR,
    Plate96,
    Tip96,
)


# ---------------- UTILITIES ----------------
def well_index_96(row_letter: str, col: int) -> int:
    row_idx = "ABCDEFGH".index(row_letter.upper())
    return (col - 1) * 8 + row_idx + 1


def mix_in_place(star, resource, well_index, volume_ul, cycles, channel=1):
    for _ in range(max(0, cycles)):
        star.aspirate(resource, [well_index], [volume_ul], channels=[channel])
        star.dispense(resource, [well_index], [volume_ul], channels=[channel])


# ---------------- MAIN PROTOCOL ----------------
def serial_dilution_1to2_96_colwise_pyhamilton():

    with HamiltonInterface(simulate=True) as ham:

        # ---------- Layout handling ----------
        if os.path.exists(LAYOUT_PATH):
            print(f"Loading layout: {LAYOUT_PATH}")
            lmgr = LayoutManager(LAYOUT_PATH)

            plate = lmgr.assign_child_resource(Plate96, PLATE_NAME)
            tip_rack = lmgr.assign_child_resource(Tip96, TIPS_NAME)
            reservoir = lmgr.assign_child_resource(Plate96, RESERVOIR_NAME)
            waste = (
                lmgr.assign_child_resource(Plate96, WASTE_NAME)
                if WASTE_NAME else None
            )
        else:
            # SAFE SIMULATION FALLBACK
            print("No .lay found → using virtual simulation resources")

            plate = Plate96(PLATE_NAME)
            tip_rack = Tip96(TIPS_NAME)
            reservoir = Plate96(RESERVOIR_NAME)
            waste = Plate96(WASTE_NAME) if WASTE_NAME else None

        # ---------- STAR ----------
        star = STAR(ham)
        star.initialize()

        channel = 1

        # ---------- PREFILL ----------
        for row in ROWS:
            star.pick_up_tips(tip_rack, tips=[channel])

            for col in range(2, N_COLS + 1):
                dst = well_index_96(row, col)

                star.aspirate(reservoir, [1], [PREFILL_VOL_UL], channels=[channel])
                star.dispense(plate, [dst], [PREFILL_VOL_UL], channels=[channel])

            star.drop_tips(tip_rack, tips=[channel])

        # ---------- SERIAL DILUTION ----------
        for row in ROWS:

            start = well_index_96(row, 1)
            star.pick_up_tips(tip_rack, tips=[channel])

            mix_in_place(
                star, plate, start,
                MIX_VOL_UL,
                PREMIX_START_CYCLES,
                channel
            )

            for col in range(1, N_COLS):
                src = well_index_96(row, col)
                dst = well_index_96(row, col + 1)

                star.aspirate(plate, [src], [TRANSFER_VOL_UL], channels=[channel])
                star.dispense(plate, [dst], [TRANSFER_VOL_UL], channels=[channel])

                mix_in_place(star, plate, dst, MIX_VOL_UL, MIX_CYCLES, channel)

            if waste is not None:
                last = well_index_96(row, N_COLS)
                star.aspirate(plate, [last], [TRANSFER_VOL_UL], channels=[channel])
                star.dispense(waste, [1], [TRANSFER_VOL_UL], channels=[channel])

            star.drop_tips(tip_rack, tips=[channel])

        star.stop()


# ---------------- RUN ----------------
if __name__ == "__main__":
    serial_dilution_1to2_96_colwise_pyhamilton()
