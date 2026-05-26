#include <stdio.h>
#include <supercode.h>

int mode_min_tie(const int *a, int n) {
    // Return the most frequent element; if there is a tie, return the smallest value.
    return super_func(int, a, n);
}

int main(void) {
    int a[] = {3, 1, 3, 1, 1};
    printf("%d\n", mode_min_tie(a, 5));
    return 0;
}
