import supercode as sc


def mode_min_tie(a: list[int]) -> int:
    # Return the most frequent element; if there is a tie, return the smallest value.
    return sc.super_func(int, a)


print(mode_min_tie([3, 1, 3, 1, 1]))
