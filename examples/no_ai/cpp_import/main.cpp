#include <iostream>
#include <supercode.hpp>

super_import_func(mode_min_tie, int, const int *a, int n);

int main() {
    int a[] = {3, 1, 3, 1, 1};
    std::cout << mode_min_tie(a, 5) << "\n";
    return 0;
}
