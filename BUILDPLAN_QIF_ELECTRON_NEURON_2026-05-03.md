# Buildplan: Quantum Integrate-and-Fire Electron Neuron

Datum: 2026-05-03
Bron: `NeuroPrompt0305`
Eigenaar: Codex
Scope: `controller/streaming_consciousness_adapter.py`

## Doel

Voeg een `SimulatedElectronNeuron` toe aan de Streaming Consciousness 11D pocket.
Deze neuron behandelt input niet als discrete bits, maar als continue complexe
amplitudes van een gesimuleerde elektron-spin. De 11D stream roteert de spin via
unitaire Pauli-rotaties. Alleen bij een expliciete drempelovergang ontstaat een
klassieke spike.

## Ontwerp

1. Electron state
   - Bewaar de qubit als complex NumPy vector `[alpha, beta]`.
   - Start in de grondtoestand `[1 + 0j, 0 + 0j]`.
   - Bewaak normalisatie en waarschijnlijkheden.

2. Integratie
   - Vertaal de 11D vector naar drie rotatiehoeken.
   - Bouw exacte unitaire matrices:
     `R_axis(theta) = cos(theta/2) I - i sin(theta/2) sigma_axis`.
   - Evolueer de state met `U = Rz @ Ry @ Rx`.

3. Meting
   - Bereken de Born-expectation langs Pauli-Z:
     `<psi|Z|psi>`.
   - Rapporteer deze waarde als quantum membraanpotentiaal.

4. Firing
   - Houd de continue quantum state gescheiden van de klassieke output.
   - De neuron vuurt alleen bij een drempelovergang vanaf een onderdrempelige
     staat naar `expectation_z >= threshold`.
   - Bij firing wordt een gemoduleerde 11D spike-vector geproduceerd en daarna
     reset de state naar de grondtoestand.

5. Integratie in de pocket
   - Maak een QIF-neuron in `StreamingConsciousness11DPocket.__init__`.
   - Verwerk elke `current_11d` door `process_stream()`.
   - Voeg QIF-status toe aan events en `get_current_state()`.

## Veiligheids- en architectuurgrenzen

- Alleen `numpy`, geen quantum SDK of externe service.
- Geen netwerk- of OS-acties.
- Geen wijziging aan bestaande dataset-feature contract tenzij expliciet nodig.
- Complexe math blijft lokaal, deterministisch en testbaar.

## Acceptatiecriteria

- Unitair evolutiestapje behoudt de norm van de state.
- Pauli-Z expectation blijft in `[-1, 1]`.
- De firing-logica is edge-triggered en reset na spike.
- Streaming events bevatten een `qif` blok.
- Docker-testset voor streaming consciousness blijft groen.
