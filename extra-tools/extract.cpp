#include <iostream>
#include <fstream>
#include <string>
#include <map>
#include <vector>
#include <windows.h>
#include <shlobj.h>

extern "C" {
#include "sqlite3.h"
}


/* 
    Built by Rev Oconner www.revoconner.com

    This is free and unencumbered software released into the public domain.

    Anyone is free to copy, modify, publish, use, compile, sell, or
    distribute this software, either in source code form or as a compiled
    binary, for any purpose, commercial or non-commercial, and by any
    means.

    In jurisdictions that recognize copyright laws, the author or authors
    of this software dedicate any and all copyright interest in the
    software to the public domain. We make this dedication for the benefit
    of the public at large and to the detriment of our heirs and
    successors. We intend this dedication to be an overt act of
    relinquishment in perpetuity of all present and future rights to this
    software under copyright law.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
    IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
    OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
    OTHER DEALINGS IN THE SOFTWARE.

*/


// To build put sqlite3.c and sqlite.h in the same folder then run with mingw64
// ren sqlite3.c sqlite3_c.c
// gcc -c sqlite3_c.c -o sqlite3.o -O2
// g++ -o PhotoExporter.exe extract.cpp sqlite3.o -lshell32 -static -O2
// ren sqlite3_c.c sqlite3.c
// pause
// this will conmpile the c file first then the cpp file


int main() {
    // Get APPDATA path
    char appdata[MAX_PATH];
    if (!GetEnvironmentVariableA("APPDATA", appdata, MAX_PATH)) {
        std::cerr << "Failed to get APPDATA path\n";
        return 1;
    }
    
    // Get Desktop path
    char desktop[MAX_PATH];
    if (FAILED(SHGetFolderPathA(NULL, CSIDL_DESKTOP, NULL, 0, desktop))) {
        std::cerr << "Failed to get Desktop path\n";
        return 1;
    }
    
    std::string db_path = std::string(appdata) + "\\facial_recognition\\face_data\\metadata.db";
    std::string csv_path = std::string(desktop) + "\\photo_paths_by_person.csv";
    
    sqlite3* db;
    if (sqlite3_open(db_path.c_str(), &db) != SQLITE_OK) {
        std::cerr << "Cannot open database: " << db_path << "\n";
        std::cerr << "Error: " << sqlite3_errmsg(db) << "\n";
        return 1;
    }
    
    // Get active clustering ID
    sqlite3_stmt* stmt;
    int clustering_id = -1;
    
    if (sqlite3_prepare_v2(db, "SELECT clustering_id FROM clusterings WHERE is_active = 1", -1, &stmt, nullptr) == SQLITE_OK) {
        if (sqlite3_step(stmt) == SQLITE_ROW) {
            clustering_id = sqlite3_column_int(stmt, 0);
        }
        sqlite3_finalize(stmt);
    }
    
    if (clustering_id == -1) {
        std::cerr << "No active clustering found\n";
        sqlite3_close(db);
        return 1;
    }
    
    // Query all persons and their photo paths
    const char* query = R"(
        SELECT 
            COALESCE(ft.tag_name, 'Person ' || ca.person_id) as name,
            p.file_path
        FROM cluster_assignments ca
        JOIN faces f ON ca.face_id = f.face_id
        JOIN photos p ON f.photo_id = p.photo_id
        LEFT JOIN face_tags ft ON ca.face_id = ft.face_id
        WHERE ca.clustering_id = ?
        ORDER BY name, p.file_path
    )";
    
    if (sqlite3_prepare_v2(db, query, -1, &stmt, nullptr) != SQLITE_OK) {
        std::cerr << "Failed to prepare query: " << sqlite3_errmsg(db) << "\n";
        sqlite3_close(db);
        return 1;
    }
    
    sqlite3_bind_int(stmt, 1, clustering_id);
    
    // Collect results
    std::map<std::string, std::vector<std::string>> persons;
    
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        const char* name = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 0));
        const char* path = reinterpret_cast<const char*>(sqlite3_column_text(stmt, 1));
        if (name && path) {
            persons[name].push_back(path);
        }
    }
    sqlite3_finalize(stmt);
    sqlite3_close(db);
    
    // Write CSV
    std::ofstream csv(csv_path);
    if (!csv.is_open()) {
        std::cerr << "Cannot create CSV file: " << csv_path << "\n";
        return 1;
    }
    
    csv << "Person,Photo Path\n";
    int total = 0;
    for (const auto& [name, paths] : persons) {
        for (const auto& path : paths) {
            // Escape quotes in CSV
            std::string escaped_path = path;
            size_t pos = 0;
            while ((pos = escaped_path.find('"', pos)) != std::string::npos) {
                escaped_path.replace(pos, 1, "\"\"");
                pos += 2;
            }
            csv << "\"" << name << "\",\"" << escaped_path << "\"\n";
            total++;
        }
    }
    csv.close();
    
    std::cout << "Exported " << total << " photos for " << persons.size() << " persons\n";
    std::cout << "Saved to: " << csv_path << "\n";
    
    return 0;
}