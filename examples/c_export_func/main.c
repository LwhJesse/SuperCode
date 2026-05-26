#include <stdio.h>
#include <supercode.h>

// Return the most frequent element; if there is a tie, return the smallest value.
super_export_func(mode_min_tie, int, const int *a, int n);

int main(void) {
    int a[] = {3, 1, 3, 1, 1};
    printf("%d\n", mode_min_tie(a, 5));
    return 0;
}
