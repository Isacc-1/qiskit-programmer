from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector


# Build a two-qubit Bell state: (|00> + |11>) / sqrt(2).
circuit = QuantumCircuit(2)
circuit.h(0)
circuit.cx(0, 1)

state = Statevector.from_instruction(circuit)
probabilities = {
    str(bitstring): float(probability)
    for bitstring, probability in state.probabilities_dict().items()
}

print("Bell-state circuit:")
print(circuit.draw())
print("Probabilities:", probabilities)
