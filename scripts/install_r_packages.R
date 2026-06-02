pkgs <- c("here", "tidyverse", "plm", "lmtest", "sandwich", "fixest",
          "boot", "ggplot2", "haven", "readxl", "patchwork",
          "modelsummary", "officer", "flextable")
install.packages(setdiff(pkgs, rownames(installed.packages())),
                 repos = "https://cloud.r-project.org")
