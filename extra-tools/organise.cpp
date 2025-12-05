// Build: g++ -o PhotosOrganise.exe organise.cpp -lole32 -lshell32 -lcomctl32 -lcomdlg32 -mwindows -static

#define UNICODE
#define _UNICODE
#include <windows.h>
#include <shlobj.h>
#include <commctrl.h>
#include <string>
#include <map>
#include <vector>
#include <fstream>

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

#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "shell32.lib")

#define ID_BTN_BROWSE_CSV    1001
#define ID_BTN_BROWSE_DEST   1002
#define ID_BTN_COPY          1003
#define ID_EDIT_CSV          1004
#define ID_EDIT_DEST         1005
#define ID_PROGRESS          1006
#define ID_STATUS            1007

HINSTANCE g_hInst;
HWND g_hwndCsvEdit, g_hwndDestEdit, g_hwndProgress, g_hwndStatus;

std::wstring GetDesktopPath() {
    wchar_t path[MAX_PATH];
    if (SUCCEEDED(SHGetFolderPathW(NULL, CSIDL_DESKTOP, NULL, 0, path))) {
        return path;
    }
    return L"";
}

std::wstring BrowseFolder(HWND hwnd) {
    wchar_t path[MAX_PATH] = {};
    BROWSEINFOW bi = {};
    bi.hwndOwner = hwnd;
    bi.pszDisplayName = path;
    bi.lpszTitle = L"Select Destination Folder";
    bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE;
    
    LPITEMIDLIST pidl = SHBrowseForFolderW(&bi);
    if (pidl) {
        SHGetPathFromIDListW(pidl, path);
        CoTaskMemFree(pidl);
        return path;
    }
    return L"";
}

std::wstring BrowseFile(HWND hwnd) {
    wchar_t path[MAX_PATH] = {};
    OPENFILENAMEW ofn = {};
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = hwnd;
    ofn.lpstrFilter = L"CSV Files\0*.csv\0All Files\0*.*\0";
    ofn.lpstrFile = path;
    ofn.nMaxFile = MAX_PATH;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST;
    
    if (GetOpenFileNameW(&ofn)) {
        return path;
    }
    return L"";
}

void SetStatus(const wchar_t* text) {
    SetWindowTextW(g_hwndStatus, text);
}

std::wstring Utf8ToWide(const std::string& utf8) {
    if (utf8.empty()) return L"";
    int size = MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), -1, NULL, 0);
    std::wstring result(size - 1, 0);
    MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), -1, &result[0], size);
    return result;
}

std::string WideToUtf8(const std::wstring& wide) {
    if (wide.empty()) return "";
    int size = WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), -1, NULL, 0, NULL, NULL);
    std::string result(size - 1, 0);
    WideCharToMultiByte(CP_UTF8, 0, wide.c_str(), -1, &result[0], size, NULL, NULL);
    return result;
}

std::string ParseCSVField(const std::string& line, size_t& pos) {
    std::string field;
    if (pos >= line.length()) return field;
    
    if (line[pos] == '"') {
        pos++;
        while (pos < line.length()) {
            if (line[pos] == '"') {
                if (pos + 1 < line.length() && line[pos + 1] == '"') {
                    field += '"';
                    pos += 2;
                } else {
                    pos++;
                    break;
                }
            } else {
                field += line[pos++];
            }
        }
        if (pos < line.length() && line[pos] == ',') pos++;
    } else {
        while (pos < line.length() && line[pos] != ',') {
            field += line[pos++];
        }
        if (pos < line.length()) pos++;
    }
    return field;
}

std::wstring SanitizeFolderName(const std::wstring& name) {
    std::wstring result;
    for (wchar_t c : name) {
        if (c == L'<' || c == L'>' || c == L':' || c == L'"' || 
            c == L'/' || c == L'\\' || c == L'|' || c == L'?' || c == L'*') {
            result += L'_';
        } else {
            result += c;
        }
    }
    while (!result.empty() && (result.back() == L' ' || result.back() == L'.')) {
        result.pop_back();
    }
    return result;
}

std::wstring GetFileName(const std::wstring& path) {
    size_t pos = path.find_last_of(L"\\/");
    if (pos != std::wstring::npos) {
        return path.substr(pos + 1);
    }
    return path;
}

bool CopyPhotos(const std::wstring& csvPath, const std::wstring& destFolder) {
    std::string csvPathUtf8 = WideToUtf8(csvPath);
    std::ifstream csv(csvPathUtf8.c_str());
    if (!csv.is_open()) {
        SetStatus(L"Cannot open CSV file");
        return false;
    }
    
    std::map<std::string, std::vector<std::string>> persons;
    std::string line;
    int lineNum = 0;
    
    while (std::getline(csv, line)) {
        lineNum++;
        if (lineNum == 1) continue;
        if (line.empty()) continue;
        
        size_t pos = 0;
        std::string person = ParseCSVField(line, pos);
        std::string photoPath = ParseCSVField(line, pos);
        
        if (!person.empty() && !photoPath.empty()) {
            persons[person].push_back(photoPath);
        }
    }
    csv.close();
    
    if (persons.empty()) {
        SetStatus(L"No data found in CSV");
        return false;
    }
    
    int totalFiles = 0;
    for (const auto& [_, paths] : persons) {
        totalFiles += (int)paths.size();
    }
    
    SendMessage(g_hwndProgress, PBM_SETRANGE, 0, MAKELPARAM(0, totalFiles));
    SendMessage(g_hwndProgress, PBM_SETPOS, 0, 0);
    
    std::wstring dest = destFolder;
    if (dest.back() != L'\\') dest += L'\\';
    
    CreateDirectoryW(dest.c_str(), NULL);
    
    int totalCopied = 0;
    int totalFailed = 0;
    int progress = 0;
    
    for (const auto& [person, paths] : persons) {
        std::wstring safeName = SanitizeFolderName(Utf8ToWide(person));
        std::wstring personFolder = dest + safeName;
        
        CreateDirectoryW(personFolder.c_str(), NULL);
        
        for (const auto& srcPath : paths) {
            std::wstring srcWide = Utf8ToWide(srcPath);
            std::wstring filename = GetFileName(srcWide);
            std::wstring destPath = personFolder + L"\\" + filename;
            
            int dupCount = 1;
            std::wstring baseDest = destPath;
            while (GetFileAttributesW(destPath.c_str()) != INVALID_FILE_ATTRIBUTES) {
                size_t dotPos = baseDest.find_last_of(L'.');
                if (dotPos != std::wstring::npos) {
                    destPath = baseDest.substr(0, dotPos) + L"_" + std::to_wstring(dupCount) + baseDest.substr(dotPos);
                } else {
                    destPath = baseDest + L"_" + std::to_wstring(dupCount);
                }
                dupCount++;
            }
            
            if (CopyFileW(srcWide.c_str(), destPath.c_str(), FALSE)) {
                totalCopied++;
            } else {
                totalFailed++;
            }
            
            progress++;
            SendMessage(g_hwndProgress, PBM_SETPOS, progress, 0);
        }
    }
    
    wchar_t msg[128];
    swprintf_s(msg, L"Done: %d copied, %d failed", totalCopied, totalFailed);
    SetStatus(msg);
    
    return true;
}

LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
        case WM_CREATE: {
            CreateWindowW(L"STATIC", L"CSV File:", WS_CHILD | WS_VISIBLE,
                10, 15, 80, 20, hwnd, NULL, g_hInst, NULL);
            
            g_hwndCsvEdit = CreateWindowW(L"EDIT", L"", 
                WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
                90, 12, 330, 24, hwnd, (HMENU)ID_EDIT_CSV, g_hInst, NULL);
            
            CreateWindowW(L"BUTTON", L"Browse", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                430, 11, 70, 26, hwnd, (HMENU)ID_BTN_BROWSE_CSV, g_hInst, NULL);
            
            CreateWindowW(L"STATIC", L"Destination:", WS_CHILD | WS_VISIBLE,
                10, 50, 80, 20, hwnd, NULL, g_hInst, NULL);
            
            g_hwndDestEdit = CreateWindowW(L"EDIT", L"", 
                WS_CHILD | WS_VISIBLE | WS_BORDER | ES_AUTOHSCROLL,
                90, 47, 330, 24, hwnd, (HMENU)ID_EDIT_DEST, g_hInst, NULL);
            
            CreateWindowW(L"BUTTON", L"Browse", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                430, 46, 70, 26, hwnd, (HMENU)ID_BTN_BROWSE_DEST, g_hInst, NULL);
            
            CreateWindowW(L"BUTTON", L"Copy Photos to Subfolders", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
                10, 90, 490, 35, hwnd, (HMENU)ID_BTN_COPY, g_hInst, NULL);
            
            g_hwndProgress = CreateWindowW(PROGRESS_CLASSW, L"", 
                WS_CHILD | WS_VISIBLE | PBS_SMOOTH,
                10, 140, 490, 20, hwnd, (HMENU)ID_PROGRESS, g_hInst, NULL);
            
            g_hwndStatus = CreateWindowW(L"STATIC", L"Ready", WS_CHILD | WS_VISIBLE,
                10, 170, 490, 20, hwnd, (HMENU)ID_STATUS, g_hInst, NULL);
            
            std::wstring defaultCsv = GetDesktopPath() + L"\\photo_paths_by_person.csv";
            SetWindowTextW(g_hwndCsvEdit, defaultCsv.c_str());
            
            return 0;
        }
        
        case WM_COMMAND: {
            switch (LOWORD(wParam)) {
                case ID_BTN_BROWSE_CSV: {
                    std::wstring file = BrowseFile(hwnd);
                    if (!file.empty()) {
                        SetWindowTextW(g_hwndCsvEdit, file.c_str());
                    }
                    break;
                }
                
                case ID_BTN_BROWSE_DEST: {
                    std::wstring folder = BrowseFolder(hwnd);
                    if (!folder.empty()) {
                        SetWindowTextW(g_hwndDestEdit, folder.c_str());
                    }
                    break;
                }
                
                case ID_BTN_COPY: {
                    wchar_t csvPath[MAX_PATH], destPath[MAX_PATH];
                    GetWindowTextW(g_hwndCsvEdit, csvPath, MAX_PATH);
                    GetWindowTextW(g_hwndDestEdit, destPath, MAX_PATH);
                    
                    if (wcslen(csvPath) == 0) {
                        MessageBoxW(hwnd, L"Please select a CSV file", L"Error", MB_ICONWARNING);
                        break;
                    }
                    if (wcslen(destPath) == 0) {
                        MessageBoxW(hwnd, L"Please select a destination folder", L"Error", MB_ICONWARNING);
                        break;
                    }
                    
                    SetStatus(L"Copying...");
                    EnableWindow(GetDlgItem(hwnd, ID_BTN_COPY), FALSE);
                    
                    if (CopyPhotos(csvPath, destPath)) {
                        MessageBoxW(hwnd, L"Photos copied successfully!", L"Complete", MB_ICONINFORMATION);
                    }
                    
                    EnableWindow(GetDlgItem(hwnd, ID_BTN_COPY), TRUE);
                    break;
                }
            }
            return 0;
        }
        
        case WM_DESTROY:
            PostQuitMessage(0);
            return 0;
    }
    return DefWindowProcW(hwnd, msg, wParam, lParam);
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE, LPSTR, int) {
    g_hInst = hInstance;
    
    INITCOMMONCONTROLSEX icex = { sizeof(icex), ICC_PROGRESS_CLASS };
    InitCommonControlsEx(&icex);
    
    WNDCLASSW wc = {};
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInstance;
    wc.lpszClassName = L"PhotoOrganizerClass";
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    RegisterClassW(&wc);
    
    HWND hwnd = CreateWindowW(L"PhotoOrganizerClass", L"Photo Organizer",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT, CW_USEDEFAULT, 525, 230,
        NULL, NULL, hInstance, NULL);
    
    ShowWindow(hwnd, SW_SHOW);
    UpdateWindow(hwnd);
    
    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }
    
    return 0;
}