# generated_protocol.py
from pyhamilton import HamiltonInterface, Plate96, Tip96

def run():
    with HamiltonInterface(simulate=True, use_simulated_hamilton=True) as ham:
        plate = Plate96("plate1", "deck1")
        tips = Tip96("tips1", "deck2")

        ham.pick_up_tips(tips)
        ham.aspirate(50, plate)
        ham.dispense(50, plate)
        ham.drop_tips(tips)

if __name__ == "__main__":
    run()