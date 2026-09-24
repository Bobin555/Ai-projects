"""Agentic loop that guesses a secret number between 1 and 100.

Each turn the agent guesses, the environment answers "too high",
"too low" or "correct", and the agent narrows its range:

  too high -> discard the guess and everything above it,
              next guess = mean(guess, lowest remaining), rounded down
  too low  -> discard the guess and everything below it,
              next guess = mean(guess, highest remaining), rounded up

Rounding direction matters: without rounding up on "too low", a range
like [g+1, g+1] would produce mean(g, g+1) -> g again and loop forever.
"""
import random

LOW, HIGH = 1, 100


def respond(secret, guess):
    """The environment: tells the agent how its guess compares."""
    if guess > secret:
        return "too high"
    if guess < secret:
        return "too low"
    return "correct"


def agent_loop(secret, low=LOW, high=HIGH, verbose=True):
    """Guess until correct. Returns the number of guesses used."""
    guess = (low + high) // 2
    for turn in range(1, high - low + 2):
        feedback = respond(secret, guess)
        if verbose:
            print(f"Guess {turn}: {guess:3d} -> {feedback}  (range {low}-{high})")
        if feedback == "correct":
            return turn
        if feedback == "too high":
            high = guess - 1
            guess = (guess + low) // 2          # mean, rounded down
        else:
            low = guess + 1
            guess = -(-(guess + high) // 2)     # mean, rounded up
    raise RuntimeError("feedback was inconsistent")


if __name__ == "__main__":
    secret = random.randint(LOW, HIGH)
    print(f"(secret is {secret})")
    n = agent_loop(secret)
    print(f"Found it in {n} guesses.")

    # Check the logic against every possible secret.
    counts = [agent_loop(s, verbose=False) for s in range(LOW, HIGH + 1)]
    print(f"All {len(counts)} secrets solved; worst case {max(counts)} guesses, "
          f"average {sum(counts) / len(counts):.2f}.")
