import pygame
import time
import sys

def test_joystick():
    pygame.init()
    pygame.joystick.init()
    
    count = pygame.joystick.get_count()
    print(f"\n[INFO] Nombre de manettes détectées : {count}")
    
    if count == 0:
        print("[ERREUR] Aucune manette n'est détectée. Vérifiez votre connexion Bluetooth.")
        return

    js = pygame.joystick.Joystick(0)
    js.init()
    print(f"[OK] Manette active : {js.get_name()}")
    print("-" * 50)
    print("Bougez les sticks ou appuyez sur les boutons (Ctrl+C pour quitter)")
    print("-" * 50)

    try:
        while True:
            pygame.event.pump()
            
            # Lecture des axes (Sticks)
            axes = []
            for i in range(js.get_numaxes()):
                val = js.get_axis(i)
                axes.append(f"A{i}:{val:>5.2f}")
            
            # Lecture des boutons
            buttons = []
            for i in range(js.get_numbuttons()):
                if js.get_button(i):
                    buttons.append(str(i))
            
            # Lecture du D-Pad (Hat)
            hats = []
            for i in range(js.get_numhats()):
                hats.append(str(js.get_hat(i)))

            # Affichage dynamique sur une seule ligne
            sys.stdout.write(f"\rAxes: {' '.join(axes)} | Boutons: {' '.join(buttons)} | Hat: {' '.join(hats)}    ")
            sys.stdout.flush()
            
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n\n[INFO] Test terminé.")
    finally:
        pygame.quit()

if __name__ == "__main__":
    test_joystick()
