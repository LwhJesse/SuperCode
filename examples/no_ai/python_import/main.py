import supercode as sc

mode_min_tie = sc.import_func("mode_min_tie", returns=int, args=[list[int]])

print(mode_min_tie([3, 1, 3, 1, 1]))
