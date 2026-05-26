#include <stddef.h>

int mode_min_tie(const int *a, int n) {
    if (a == NULL || n <= 0) {
        return 0;
    }
    int best_value = a[0];
    int best_count = 0;
    for (int i = 0; i < n; ++i) {
        int count = 0;
        for (int j = 0; j < n; ++j) {
            if (a[j] == a[i]) {
                ++count;
            }
        }
        if (count > best_count || (count == best_count && a[i] < best_value)) {
            best_count = count;
            best_value = a[i];
        }
    }
    return best_value;
}
