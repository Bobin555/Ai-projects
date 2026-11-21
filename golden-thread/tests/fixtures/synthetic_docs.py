"""Text of the synthetic documents. Later tests quote these sentences exactly."""
from fixtures.pdfs import Heading, ImageOnly, Para, Table

CRITERION_10 = (
    "The reactor core shall be designed so that fuel design limits are not exceeded during normal "
    "operation and anticipated operational occurrences, with appropriate margin for uncertainties."
)

DOCS = {
    "SYN-RG1@r1": [
        [Heading("1 Scope"), Para("This guide applies to modular reactors."),
         Heading("2 Criteria"), Heading("2.1 Criterion 10"), Para(CRITERION_10)],
        [Table([["Criterion", "Topic"], ["10", "Reactor design"], ["16", "Containment"]]),
         Heading("2.2 Criterion 11"),
         Para("The reactor shall have inherent protection against reactivity increases.")],
        [ImageOnly()],
    ],
    "SYN-SAR@r1": [
        [Heading("3.2 Fuel"), Para("The fuel temperature limit is 1600 C.")],
    ],
    "SYN-SAR@r2": [
        [Heading("3.2 Fuel"), Para("The fuel temperature limit is 1650 C."),
         Para("The design meets Criterion 10 because the core keeps fuel below the limit."),
         Para("Fuel performance is confirmed in report TR-123."),
         Para("Burnup data are [[ proprietary ]] and withheld.")],
        [Heading("4 Licensing"), Para("10 CFR 50.34(a) requires a preliminary safety analysis report."),
         Para("Section 50.34(b) is outside the scope of this report.")],
    ],
    "SYN-SE@r1": [
        [Heading("4 Evaluation"),
         Para("The staff finds the fuel design acceptable for PDC 10, subject to Condition 1."),
         Para("Condition 1: The applicant shall confirm the temperature limit before operation.")],
    ],
}
