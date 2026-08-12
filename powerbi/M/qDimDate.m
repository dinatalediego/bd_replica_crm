let
    Today = Date.From(DateTime.LocalNow()),
    StartDate = Date.StartOfYear(Date.AddYears(Today, -2)),
    EndDate = Date.EndOfYear(Date.AddYears(Today, 1)),
    DayCount = Duration.Days(EndDate - StartDate) + 1,
    Dates = List.Dates(StartDate, DayCount, #duration(1, 0, 0, 0)),
    Table0 = Table.FromList(Dates, Splitter.SplitByNothing(), {"Date"}),
    Types = Table.TransformColumnTypes(Table0, {{"Date", type date}}),
    AddYear = Table.AddColumn(Types, "Year", each Date.Year([Date]), Int64.Type),
    AddMonthNo = Table.AddColumn(AddYear, "MonthNo", each Date.Month([Date]), Int64.Type),
    AddMonth = Table.AddColumn(AddMonthNo, "Month", each Date.ToText([Date], "MMM", "es-PE"), type text),
    AddYearMonth = Table.AddColumn(AddMonth, "YearMonth", each Date.ToText([Date], "yyyy-MM"), type text),
    AddWeek = Table.AddColumn(AddYearMonth, "WeekOfYear", each Date.WeekOfYear([Date], Day.Monday), Int64.Type),
    AddDay = Table.AddColumn(AddWeek, "Day", each Date.Day([Date]), Int64.Type),
    AddWeekday = Table.AddColumn(AddDay, "Weekday", each Date.DayOfWeekName([Date], "es-PE"), type text),
    AddIsToday = Table.AddColumn(AddWeekday, "IsToday", each [Date] = Today, type logical)
in
    AddIsToday
